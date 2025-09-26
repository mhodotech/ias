# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Define all the related fields in product.template with 'readonly=False'
    # to be able to modify the values from product.template.

    nmfc_code = fields.Char(
        string="NMFC Code",
        related="product_variant_ids.nmfc_code",
        help="National Motor Freight Classification code",
        readonly=False,
    )

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
        related="product_variant_ids.freight_class",
        help="Freight classification based on density, stowability, handling, and liability",
        readonly=False,
    )

    # Alternative: If using char field
    # freight_class = fields.Char(
    #     string="Freight Class",
    #     related="product_variant_ids.freight_class",
    #     help="Freight classification (typically 50-500)",
    #     readonly=False,
    # )

    commodity_description = fields.Text(
        string="Commodity Description",
        related="product_variant_ids.commodity_description",
        help="Detailed description of the commodity for freight classification",
        readonly=False,
    )

    def _prepare_variant_values(self, combination):
        """
        As variant is created inside template create() method and as
        template fields values are flushed after _create_variant_ids(),
        we catch the variant values preparation to update them
        """
        res = super()._prepare_variant_values(combination)

        if self.nmfc_code:
            res.update({"nmfc_code": self.nmfc_code})
        if self.freight_class:
            res.update({"freight_class": self.freight_class})
        if self.commodity_description:
            res.update({"commodity_description": self.commodity_description})

        return res