# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Special services section
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

    carrier_id = fields.Many2one(
        'delivery.carrier',
        string='Carrier',
        help='The carrier responsible for this shipment'
    )

    # Carrier information
    carrier_tracking_ref = fields.Char(
        string='PRO Number',
        copy=False,
        tracking=True
    )

    # Related shipment rates
    shipment_rate_ids = fields.One2many(
        'shipment.rate',
        'picking_id',
        string='Shipment Rates'
    )

    shipment_rate_count = fields.Integer(
        string='Rate Count',
        compute='_compute_shipment_rate_count'
    )

    shipment_number = fields.Char(
        string='Shipment #',
        default=lambda self: self._generate_shipment_number(),
        copy=False,
        readonly=True,
        tracking=True
    )
    third_party_freight_partner_id = fields.Many2one(
        'res.partner',
        string='Third Party Freight Charges Billed To',
        compute='_compute_third_party_freight_partner',
        store=True,
        readonly=False,
        tracking=True
    )
    trailer_number = fields.Char(string='Trailer Number', tracking=True)
    seal_number = fields.Char(string='Seal Number', tracking=True)
    freight_charge_terms = fields.Char(
        string='Freight Charge Terms',
        default='Prepaid',
        tracking=True
    )
    master_bill_of_lading = fields.Boolean(
        string='Master Bill of Lading',
        default=False,
        tracking=True
    )

    fob_ship_from = fields.Boolean(string='FOB Ship From', default=False)
    fob_ship_to = fields.Boolean(string='FOB Ship To', default=False)

    @api.model
    def _generate_shipment_number(self):
        """Generate a unique 7-digit shipment number"""
        import random
        while True:
            number = str(random.randint(1000000, 9999999))
            if not self.search([('shipment_number', '=', number)], limit=1):
                return number

    @api.depends('partner_id')
    def _compute_third_party_freight_partner(self):
        for picking in self:
            partner = self.env['res.partner'].search([
                ('third_party_freight_billing', '=', True)
            ], limit=1)
            if partner and not picking.third_party_freight_partner_id:
                picking.third_party_freight_partner_id = partner

    @api.depends('shipment_rate_ids')
    def _compute_shipment_rate_count(self):
        for picking in self:
            picking.shipment_rate_count = len(picking.shipment_rate_ids)

    def action_view_shipment_rates(self):
        """Open shipment rates view"""
        self.ensure_one()
        return {
            'name': _('Shipment Rates'),
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'res_model': 'shipment.rate',
            'domain': [('picking_id', '=', self.id)],
            'context': {'default_picking_id': self.id},
        }

    def action_put_in_pack(self):
        """Override to open our custom wizard"""
        self.ensure_one()

        # Get move lines that have quantity and are not already in a package
        move_line_ids = self.move_line_ids.filtered(
            lambda ml: ml.quantity > 0 and not ml.result_package_id
        )

        # If there are move lines with picked flag, use only those
        picked_lines = move_line_ids.filtered(lambda ml: ml.picked)
        if picked_lines:
            move_line_ids = picked_lines

        if not move_line_ids:
            raise UserError(
                _('There is nothing to put in a pack. Either mark products as picked or ensure they have quantities.'))

        # Get default package type
        package_type = self.env['stock.package.type'].search([], limit=1)
        if not package_type:
            package_type = self.env['stock.package.type'].create({
                'name': 'Default Package',
                'barcode': 'PACK',
            })

        # Get default commodity description
        default_commodity = self.env['commodity.description'].search([], limit=1)

        commodity_description = default_commodity  # fallback to default
        if move_line_ids and move_line_ids[0].product_id.nmfc_description_id:
            commodity_description = move_line_ids[0].product_id.nmfc_description_id

        # Calculate default weight
        product_weight = sum(move_line_ids.mapped(
            lambda ml: ml.quantity * ml.product_id.weight
        ))
        package_weight = package_type.max_weight if package_type else 0
        total_weight = product_weight + package_weight or 1.0  # Default to 1 if zero

        # Create wizard with all required fields
        wizard_vals = {
            'picking_id': self.id,
            'move_line_ids': [(6, 0, move_line_ids.ids)],
            'package_type_id': package_type.id,
            'nmfc_class': '85',
            'span_package_qty': 1,
            'commodity_description_id': commodity_description.id if commodity_description else False,
            'shipping_weight': total_weight,
            'shipping_length': package_type.packaging_length or 48,
            'shipping_width': package_type.width or 40,
            'shipping_height': package_type.height or 48,
        }

        # Override with product defaults if available
        if move_line_ids and move_line_ids[0].product_id:
            product = move_line_ids[0].product_id
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
        """Open get rates wizard"""
        self.ensure_one()

        # Check if all products are in packages
        move_lines_without_package = self.move_line_ids.filtered(
            lambda ml: ml.quantity > 0 and not ml.result_package_id
        )

        if move_lines_without_package:
            raise UserError(_('All products must be in packages before getting rates. Please use Put in Pack first.'))

        # Get all packages from move lines
        packages = self.move_line_ids.mapped('result_package_id')

        if not packages:
            raise UserError(_('No packages found. Please put products in packages first.'))

        # Create the wizard with the correct fields from your wizard
        wizard = self.env['get.rates.wizard'].create({
            'picking_id': self.id,
            'package_ids': [(6, 0, packages.ids)],  # Pass the packages
            'carrier_type': 'ltl',  # Default to LTL
            'requires_liftgate': self.requires_liftgate if hasattr(self, 'requires_liftgate') else False,
            'requires_inside_delivery': self.requires_inside_delivery if hasattr(self,
                                                                                 'requires_inside_delivery') else False,
            'shipping_notes': self.shipping_notes if hasattr(self, 'shipping_notes') else '',
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

    def _propagate_shipping_info(self):
        """Propagate shipping info to all related transfers in the chain"""
        for picking in self:
            if not picking.carrier_id or not picking.carrier_tracking_ref:
                continue

            # Get all related pickings through backorder and move relationships
            related_pickings = self.env['stock.picking']

            # Find pickings linked through the same sale order
            if picking.sale_id:
                related_pickings |= self.env['stock.picking'].search([
                    ('sale_id', '=', picking.sale_id.id),
                    ('id', '!=', picking.id)
                ])

            # Find pickings linked through move destinations
            for move in picking.move_ids:
                if move.move_dest_ids:
                    related_pickings |= move.move_dest_ids.mapped('picking_id')

            # Find pickings that have this picking's moves as origins
            origin_moves = self.env['stock.move'].search([
                ('move_orig_ids', 'in', picking.move_ids.ids)
            ])
            related_pickings |= origin_moves.mapped('picking_id')

            # Update all related pickings with shipping info
            for related_picking in related_pickings:
                if not related_picking.carrier_id:
                    related_picking.write({
                        'carrier_id': picking.carrier_id.id,
                        'carrier_tracking_ref': picking.carrier_tracking_ref,
                        'requires_liftgate': picking.requires_liftgate,
                        'requires_inside_delivery': picking.requires_inside_delivery,
                        'shipping_notes': picking.shipping_notes,
                    })

    def button_validate(self):
        """Override to propagate shipping info when validating"""
        res = super().button_validate()

        # Propagate shipping info to next transfers
        self._propagate_shipping_info()

        # Find and update any newly created transfers
        if res and isinstance(res, dict) and res.get('res_model') == 'stock.immediate.transfer':
            # After immediate transfer, propagate to new pickings
            self.env.cr.commit()  # Ensure the transfer is completed
            self._propagate_shipping_info()

        return res

    def write(self, vals):
        """Override write to propagate shipping changes"""
        res = super().write(vals)

        # If shipping info is updated, propagate to related transfers
        if any(field in vals for field in ['carrier_id', 'carrier_tracking_ref',
                                           'requires_liftgate', 'requires_inside_delivery',
                                           'shipping_notes']):
            self._propagate_shipping_info()

        return res

    def get_customer_po_for_bol(self):
        """Helper method to get customer PO for Bill of Lading"""
        self.ensure_one()
        _logger.info(f"Getting customer PO for picking {self.name}")
        _logger.info(f"Has sale_id: {bool(self.sale_id)}")

        if self.sale_id:
            _logger.info(f"Sale order: {self.sale_id.name}")
            _logger.info(f"Has gp_cstponbr field: {hasattr(self.sale_id, 'gp_cstponbr')}")

            if hasattr(self.sale_id, 'gp_cstponbr'):
                _logger.info(f"gp_cstponbr value: {self.sale_id.gp_cstponbr}")
                if self.sale_id.gp_cstponbr:
                    return self.sale_id.gp_cstponbr

            if self.sale_id.client_order_ref:
                return self.sale_id.client_order_ref

        return self.origin or ''

    def get_packages_grouped_for_bol(self):
        """Helper method to get packages grouped by type for BOL"""
        self.ensure_one()
        packages_by_type = {}
        customer_po = self.get_customer_po_for_bol()

        _logger.info(f"Grouping packages for picking {self.name}")
        _logger.info(f"Customer PO: {customer_po}")

        # Get unique packages (not move lines!)
        packages = self.move_line_ids.mapped('result_package_id')
        _logger.info(f"Number of unique packages: {len(packages)}")

        for package in packages:
            _logger.info(f"Found package: {package.name}")
            _logger.info(f"Package type: {package.package_type_id.name if package.package_type_id else 'NO TYPE'}")
            _logger.info(f"Span package qty: {package.span_package_qty}")
            _logger.info(f"Shipping weight: {package.shipping_weight}")

            pkg_type = package.package_type_id.name if package.package_type_id else 'PACKAGE'

            if pkg_type not in packages_by_type:
                packages_by_type[pkg_type] = {
                    'units': 0,  # Count of packages
                    'pkgs': 0,  # Sum of span_package_qty
                    'weight': 0.0,  # Sum of shipping_weight
                    'customer_po': customer_po,
                    'picking_name': self.name
                }

            # Each package counts as 1 unit
            packages_by_type[pkg_type]['units'] += 1
            # Add the span_package_qty from this package
            packages_by_type[pkg_type]['pkgs'] += package.span_package_qty or 0
            # Add the shipping_weight from this package
            packages_by_type[pkg_type]['weight'] += package.shipping_weight or 0.0

        _logger.info(f"Grouped packages result: {packages_by_type}")
        return packages_by_type