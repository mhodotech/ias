# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    # NMFC (National Motor Freight Classification) field
    nmfc_code = fields.Char(
        string="NMFC Code",
        help="National Motor Freight Classification code"
    )

    # Class field - typically ranges from 50 to 500
    freight_class = fields.Selection([
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
    ],
        string="Freight Class",
        help="Freight classification based on density, stowability, handling, and liability"
    )

    # Alternative: If you prefer a simple char field for flexibility
    # freight_class = fields.Char(
    #     string="Freight Class",
    #     help="Freight classification (typically 50-500)"
    # )

    # Commodity Description field
    commodity_description = fields.Text(
        string="Commodity Description",
        help="Detailed description of the commodity for freight classification"
    )