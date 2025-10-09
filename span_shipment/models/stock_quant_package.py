# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    # Shipping dimensions (in inches)
    shipping_length = fields.Float(
        string='Length (in)',
        help='Package length in inches'
    )
    shipping_width = fields.Float(
        string='Width (in)',
        help='Package width in inches'
    )
    shipping_height = fields.Float(
        string='Height (in)',
        help='Package height in inches'
    )
    shipping_weight = fields.Float(
        string='Shipping Weight (lbs)',
        help='Total shipping weight including package'
    )

    # PCF - Auto-calculated
    pcf = fields.Float(
        string='PCF',
        compute='_compute_pcf',
        store=True,
        help='Pounds per Cubic Foot'
    )

    # NMFC fields
    nmfc_code = fields.Char(
        string='NMFC Code'
    )

    nmfc_class = fields.Selection([
        ('50', 'Class 50'),
        ('55', 'Class 55'),
        ('60', 'Class 60'),
        ('65', 'Class 65'),
        ('70', 'Class 70'),
        ('77.5', 'Class 77.5'),
        ('85', 'Class 85'),
        ('92.5', 'Class 92.5'),
        ('100', 'Class 100'),
        ('110', 'Class 110'),
        ('125', 'Class 125'),
        ('150', 'Class 150'),
        ('175', 'Class 175'),
        ('200', 'Class 200'),
        ('250', 'Class 250'),
        ('300', 'Class 300'),
        ('400', 'Class 400'),
        ('500', 'Class 500'),
    ], string='Freight Class', required=True)

    # Commodity description
    commodity_description_id = fields.Many2one(
        'commodity.description',
        string='NMFC Description'
    )

    # Span package info
    span_package_type_id = fields.Many2one(
        'span.package.type',
        string='Span Package Type'
    )
    span_package_qty = fields.Integer(
        string='Span Quantity',
        default=1,
        help='Number of span packages within this package'
    )

    # Special handling
    is_hazmat = fields.Boolean(
        string='Hazardous Material'
    )
    special_handling = fields.Text(
        string='Special Handling Instructions'
    )

    # Shipment status
    is_shipped = fields.Boolean(
        string='Shipped',
        default=False,
        help='Package has been shipped and cannot be modified'
    )

    @api.depends('shipping_length', 'shipping_width', 'shipping_height', 'shipping_weight')
    def _compute_pcf(self):
        """Calculate PCF based on actual package dimensions and weight"""
        for package in self:
            if all([package.shipping_length, package.shipping_width,
                    package.shipping_height, package.shipping_weight]):
                cubic_inches = package.shipping_length * package.shipping_width * package.shipping_height
                cubic_feet = cubic_inches / 1728.0

                if cubic_feet > 0:
                    package.pcf = package.shipping_weight / cubic_feet
                else:
                    package.pcf = 0.0
            else:
                package.pcf = 0.0

    @api.constrains('shipping_weight', 'shipping_length', 'shipping_width', 'shipping_height', 'nmfc_class')
    def _check_modification_allowed(self):
        """Check if package can be modified"""
        for package in self:
            if package.is_shipped:
                raise ValidationError(_('Cannot modify package %s - it has already been shipped.') % package.name)

            # Check if package has active rates
            active_rates = self.env['shipment.rate'].search([
                ('package_ids', 'in', package.id),
                ('state', '=', 'active')
            ])
            if active_rates and not self.env.context.get('force_write'):
                raise UserError(_(
                    'Cannot modify package %s - it has active rates. '
                    'Please expire or delete the rates first.'
                ) % package.name)

    def unlink(self):
        """Prevent deletion of shipped packages"""
        for package in self:
            if package.is_shipped:
                raise UserError(_('Cannot delete package %s - it has already been shipped.') % package.name)
        return super().unlink()

    def get_picking(self):
        """Get the picking associated with this package"""
        self.ensure_one()
        move_lines = self.env['stock.move.line'].search([
            ('result_package_id', '=', self.id)
        ])
        if move_lines:
            return move_lines[0].picking_id
        return False