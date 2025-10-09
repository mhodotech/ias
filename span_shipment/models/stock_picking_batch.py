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