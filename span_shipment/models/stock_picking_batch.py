# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'

    # Additional info tab fields
    carrier_id = fields.Many2one(
        'delivery.carrier',
        string='Carrier'
    )
    carrier_tracking_ref = fields.Char(
        string='PRO Number',
        copy=False
    )
    total_shipping_weight = fields.Float(
        string='Total Weight',
        compute='_compute_total_weight'
    )
    related_sale_orders = fields.Char(
        string='Sales Orders',
        compute='_compute_related_orders'
    )

    # Related shipment rates
    shipment_rate_ids = fields.One2many(
        'shipment.rate',
        'batch_id',
        string='Shipment Rates'
    )

    shipment_rate_count = fields.Integer(
        string='Rate Count',
        compute='_compute_shipment_rate_count'
    )

    package_ids = fields.Many2many(
        'stock.quant.package',
        compute='_compute_package_ids',
        string='Packages'
    )
    package_count = fields.Integer(
        string='Package Count',
        compute='_compute_package_ids'
    )

    requires_liftgate = fields.Boolean(
        string='Liftgate Required',
        tracking=True
    )
    requires_inside_delivery = fields.Boolean(
        string='Inside Delivery',
        tracking=True
    )
    shipping_notes = fields.Text(
        string='Shipping Notes',
        help='Special instructions for shipping'
    )

    shipment_number = fields.Char(
        string='Shipment #',
        compute='_compute_shipment_number',
        store=True,
        readonly=False
    )
    third_party_freight_partner_id = fields.Many2one(
        'res.partner',
        string='Third Party Freight Charges Billed To',
        compute='_compute_third_party_freight_partner',
        store=True,
        readonly=False
    )
    trailer_number = fields.Char(string='Trailer Number')
    seal_number = fields.Char(string='Seal Number')
    freight_charge_terms = fields.Char(
        string='Freight Charge Terms',
        default='Prepaid'
    )
    master_bill_of_lading = fields.Boolean(
        string='Master Bill of Lading',
        default=False
    )

    fob_ship_from = fields.Boolean(string='FOB Ship From', default=False)
    fob_ship_to = fields.Boolean(string='FOB Ship To', default=False)


    @api.depends('picking_ids.shipment_number')
    def _compute_shipment_number(self):
        for batch in self:
            if batch.picking_ids:
                batch.shipment_number = batch.picking_ids[0].shipment_number

    @api.depends('picking_ids.partner_id')
    def _compute_third_party_freight_partner(self):
        for batch in self:
            partner = self.env['res.partner'].search([
                ('third_party_freight_billing', '=', True)
            ], limit=1)
            if partner and not batch.third_party_freight_partner_id:
                batch.third_party_freight_partner_id = partner

    def _get_packages_by_type(self):
        """Group packages by packaging type (handling unit) for Customer Order Information table"""
        package_groups = {}

        # Get all packages from all pickings in the batch
        all_packages = self.env['stock.quant.package']
        for picking in self.picking_ids:
            all_packages |= picking.move_line_ids.mapped('result_package_id')

        # Group by packaging type (handling unit type like PALLET, CARTON)
        for package in all_packages:
            pkg_type = package.package_type_id.name if package.package_type_id else 'PACKAGE'
            if pkg_type not in package_groups:
                package_groups[pkg_type] = {
                    'units': 0,  # Count of handling units (packages)
                    'pkgs': 0,  # Total span_package_qty
                    'weight': 0.0,
                    'customer_po': '',
                    'picking_name': ''
                }

            # Find the picking for this package
            picking = self.picking_ids.filtered(lambda p: package in p.move_line_ids.mapped('result_package_id'))
            if picking:
                picking = picking[0]
                if not package_groups[pkg_type]['customer_po']:
                    package_groups[pkg_type][
                        'customer_po'] = picking.sale_id.gp_cstponbr or picking.sale_id.client_order_ref or ''
                    package_groups[pkg_type]['picking_name'] = picking.name

            package_groups[pkg_type]['units'] += 1  # One handling unit
            package_groups[pkg_type]['pkgs'] += package.span_package_qty or 0
            package_groups[pkg_type]['weight'] += package.shipping_weight or 0.0

        return list(package_groups.values())

    @api.depends('picking_ids.move_line_ids.result_package_id')
    def _compute_package_ids(self):
        for batch in self:
            packages = batch.picking_ids.mapped('move_line_ids.result_package_id')
            batch.package_ids = packages
            batch.package_count = len(packages)

    def action_view_packages(self):
        """View packages in this batch"""
        self.ensure_one()
        packages = self.package_ids
        return {
            'name': _('Packages'),
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'stock.quant.package',
            'domain': [('id', 'in', packages.ids)],
        }

    @api.depends('picking_ids.move_line_ids.result_package_id.shipping_weight')
    def _compute_total_weight(self):
        for batch in self:
            # Get all packages from all pickings in the batch
            packages = batch.picking_ids.mapped('move_line_ids.result_package_id')
            batch.total_shipping_weight = sum(packages.mapped('shipping_weight'))

    @api.depends('picking_ids')
    def _compute_related_orders(self):
        for batch in self:
            sale_orders = []
            for picking in batch.picking_ids:
                # Try multiple ways to get sale order reference
                if hasattr(picking, 'sale_id') and picking.sale_id:
                    sale_orders.append(picking.sale_id.name)
                elif picking.origin:
                    # Origin might be a sale order name
                    sale_orders.append(picking.origin)
            # Remove duplicates
            sale_orders = list(dict.fromkeys(sale_orders))
            batch.related_sale_orders = ', '.join(sale_orders) if sale_orders else ''

    @api.depends('shipment_rate_ids')
    def _compute_shipment_rate_count(self):
        for batch in self:
            batch.shipment_rate_count = len(batch.shipment_rate_ids)

    def action_view_shipment_rates(self):
        """Open shipment rates view"""
        self.ensure_one()
        return {
            'name': _('Shipment Rates'),
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'shipment.rate',
            'domain': [('batch_id', '=', self.id)],
            'context': {'default_batch_id': self.id},
        }

    def action_put_in_pack(self):
        """Open put in pack wizard for batch"""
        # Get picked lines from all pickings
        picked_lines = self.env['stock.move.line']
        for picking in self.picking_ids:
            picked_lines |= picking.move_line_ids.filtered(
                lambda ml: ml.quantity > 0 and not ml.result_package_id and ml.picked
            )

        if not picked_lines:
            raise UserError(_('Please mark at least one product as picked before creating a package.'))

        # Get defaults
        package_type = self.env['stock.package.type'].search([], limit=1)
        if not package_type:
            package_type = self.env['stock.package.type'].create({
                'name': 'Default Package',
                'barcode': 'PACK',
            })

        # Get commodity description from products if available
        default_commodity = self.env['commodity.description'].search([], limit=1)
        commodity_description = default_commodity

        if picked_lines and picked_lines[0].product_id.nmfc_description_id:
            commodity_description = picked_lines[0].product_id.nmfc_description_id

        # Calculate weight
        product_weight = sum(picked_lines.mapped(
            lambda ml: ml.quantity * ml.product_id.weight
        ))
        package_weight = package_type.max_weight if package_type else 0
        total_weight = product_weight + package_weight or 1.0

        # Create wizard
        wizard_vals = {
            'batch_id': self.id,
            'move_line_ids': [(6, 0, picked_lines.ids)],
            'package_type_id': package_type.id,
            'commodity_description_id': commodity_description.id if commodity_description else False,
            'shipping_weight': total_weight,
            'shipping_length': package_type.packaging_length or 48,
            'shipping_width': package_type.width or 40,
            'shipping_height': package_type.height or 48,
            'nmfc_class': '85',
            'span_package_qty': 1,
        }

        # Override with product defaults if available
        if picked_lines and picked_lines[0].product_id:
            product = picked_lines[0].product_id
            if product.product_length:
                wizard_vals['shipping_length'] = product.product_length
            if product.product_width:
                wizard_vals['shipping_width'] = product.product_width
            if product.product_height:
                wizard_vals['shipping_height'] = product.product_height
            if product.nmfc_code:
                wizard_vals['nmfc_code'] = product.nmfc_code
            if product.nmfc_class:
                wizard_vals['nmfc_class'] = product.nmfc_class
            if product.nmfc_description_id:
                wizard_vals['commodity_description_id'] = product.nmfc_description_id.id

        wizard = self.env['put.in.pack.wizard'].create(wizard_vals)

        return {
            'name': _('Put in Pack'),
            'type': 'ir.actions.act_window',
            'res_model': 'put.in.pack.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_get_rates(self):
        """Open get rates wizard for batch"""
        # Get all packages from all pickings
        packages = self.env['stock.quant.package']

        for picking in self.picking_ids:
            # Check for unpacked items - corrected check
            unpacked_lines = picking.move_line_ids.filtered(
                lambda ml: ml.quantity > 0 and not ml.result_package_id
            )
            if unpacked_lines:
                raise UserError(_(
                    'All products must be in packages before getting rates. '
                    'Picking %s has products not in packages.'
                ) % picking.name)

            # Collect all packages
            packages |= picking.move_line_ids.mapped('result_package_id')

        if not packages:
            raise UserError(_('No packages found. Please create packages first.'))

        # Check that all pickings have same destination
        partners = self.picking_ids.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(_('All pickings in batch must have the same delivery address.'))

        # Create wizard with special services from batch
        wizard = self.env['get.rates.wizard'].create({
            'batch_id': self.id,
            'package_ids': [(6, 0, packages.ids)],
            'carrier_type': 'ltl',  # Default to LTL
            'requires_liftgate': self.requires_liftgate,
            'requires_inside_delivery': self.requires_inside_delivery,
            'shipping_notes': self.shipping_notes,
        })

        # Set default carrier if available
        nexterus = self.env['delivery.carrier'].search([
            ('delivery_type', '=', 'nexterus')
        ], limit=1)
        if nexterus:
            wizard.delivery_carrier_id = nexterus

        return {
            'name': _('Get Shipping Rates'),
            'type': 'ir.actions.act_window',
            'res_model': 'get.rates.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def write(self, vals):
        """Override write to propagate carrier and tracking ref to pickings"""
        res = super(StockPickingBatch, self).write(vals)

        # Check if carrier_id or carrier_tracking_ref is being updated
        if 'carrier_id' in vals or 'carrier_tracking_ref' in vals:
            for batch in self:
                picking_vals = {}

                # Only update if the field was changed in batch
                if 'carrier_id' in vals:
                    picking_vals['carrier_id'] = vals['carrier_id']
                if 'carrier_tracking_ref' in vals:
                    picking_vals['carrier_tracking_ref'] = vals['carrier_tracking_ref']

                if picking_vals:
                    # Update only pickings where these fields are empty
                    pickings_to_update = batch.picking_ids.filtered(
                        lambda p: (not p.carrier_id if 'carrier_id' in picking_vals else True) and
                                  (not p.carrier_tracking_ref if 'carrier_tracking_ref' in picking_vals else True)
                    )
                    if pickings_to_update:
                        pickings_to_update.write(picking_vals)

        return res

    def get_packages_grouped_for_bol(self):
        """Helper method to get packages grouped by type for BOL - returns dict like picking"""
        self.ensure_one()
        packages_by_type = {}

        # Get all unique packages from all pickings
        all_packages = self.package_ids  # This already gives unique packages

        for package in all_packages:
            # Find ALL pickings this package belongs to (not just first)
            related_pickings = self.picking_ids.filtered(
                lambda p: package in p.move_line_ids.mapped('result_package_id')
            )

            # Collect customer POs and picking names from all related pickings
            customer_pos = []
            picking_names = []

            for picking in related_pickings:
                # Get customer PO using the same logic as picking
                if picking.sale_id:
                    # Use gp_cstponbr first, then client_order_ref as fallback
                    if hasattr(picking.sale_id, 'gp_cstponbr') and picking.sale_id.gp_cstponbr:
                        customer_po = picking.sale_id.gp_cstponbr
                    else:
                        customer_po = picking.sale_id.client_order_ref or ''
                else:
                    customer_po = picking.origin or ''

                if customer_po and customer_po not in customer_pos:
                    customer_pos.append(customer_po)

                if picking.name not in picking_names:
                    picking_names.append(picking.name)

            # Join multiple POs and picking names with comma
            customer_po_str = ', '.join(customer_pos) if customer_pos else ''
            picking_names_str = ', '.join(picking_names) if picking_names else ''

            pkg_type = package.package_type_id.name if package.package_type_id else 'PACKAGE'

            if pkg_type not in packages_by_type:
                packages_by_type[pkg_type] = {
                    'units': 0,
                    'pkgs': 0,
                    'weight': 0.0,
                    'customer_po': customer_po_str,
                    'picking_name': picking_names_str
                }
            else:
                # If we already have this package type, we might need to append POs
                # This handles case where multiple packages of same type have different POs
                existing_pos = packages_by_type[pkg_type]['customer_po'].split(', ') if packages_by_type[pkg_type][
                    'customer_po'] else []
                existing_pickings = packages_by_type[pkg_type]['picking_name'].split(', ') if \
                packages_by_type[pkg_type]['picking_name'] else []

                for po in customer_pos:
                    if po and po not in existing_pos:
                        existing_pos.append(po)

                for name in picking_names:
                    if name and name not in existing_pickings:
                        existing_pickings.append(name)

                packages_by_type[pkg_type]['customer_po'] = ', '.join(existing_pos)
                packages_by_type[pkg_type]['picking_name'] = ', '.join(existing_pickings)

            packages_by_type[pkg_type]['units'] += 1
            packages_by_type[pkg_type]['pkgs'] += package.span_package_qty or 0
            packages_by_type[pkg_type]['weight'] += package.shipping_weight or 0.0

        return packages_by_type