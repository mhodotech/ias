# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Dimension fields (in inches)
    product_length = fields.Float(
        string='Length (in)',
        help='Product length in inches'
    )
    product_width = fields.Float(
        string='Width (in)',
        help='Product width in inches'
    )
    product_height = fields.Float(
        string='Height (in)',
        help='Product height in inches'
    )

    # PCF (Pounds per Cubic Foot) - Auto-calculated
    pcf = fields.Float(
        string='PCF',
        compute='_compute_pcf',
        store=True,
        help='Pounds per Cubic Foot (density)'
    )

    # NMFC fields
    nmfc_code = fields.Char(
        string='NMFC Code',
        help='National Motor Freight Classification code'
    )
    nmfc_description_id = fields.Many2one(
    'commodity.description',
    string='NMFC Description'
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
    ], string='Freight Class')

    # Special handling
    is_hazmat = fields.Boolean(
        string='Hazardous Material',
        help='Check if this product contains hazardous materials'
    )
    special_handling = fields.Text(
        string='Special Handling Instructions'
    )

    @api.depends('product_length', 'product_width', 'product_height', 'weight')
    def _compute_pcf(self):
        """Calculate PCF (Pounds per Cubic Foot)"""
        for product in self:
            if product.product_length and product.product_width and product.product_height and product.weight:
                # Calculate cubic feet
                cubic_inches = product.product_length * product.product_width * product.product_height
                cubic_feet = cubic_inches / 1728.0

                if cubic_feet > 0:
                    product.pcf = product.weight / cubic_feet
                else:
                    product.pcf = 0.0
            else:
                product.pcf = 0.0

    @api.depends('product_length', 'product_width', 'product_height')
    def _compute_volume(self):
        """Override to compute volume in cubic feet from dimensions in inches"""
        for product in self:
            if product.product_length and product.product_width and product.product_height:
                cubic_inches = product.product_length * product.product_width * product.product_height
                product.volume = cubic_inches / 1728.0  # Convert to cubic feet
            else:
                super(ProductTemplate, product)._compute_volume()