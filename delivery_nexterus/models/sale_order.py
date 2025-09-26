# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Minimal Nexterus fields needed for quote tracking
    nexterus_quote_id = fields.Char(
        string='Nexterus Quote ID',
        copy=False,
        readonly=True,
        help='Quote ID from Nexterus rate request'
    )

    nexterus_carrier_price = fields.Float(
        string='Nexterus Carrier Price',
        copy=False,
        readonly=True,
        help='Original price from Nexterus before margin'
    )

    # These are kept temporarily for backward compatibility but will be phased out
    nexterus_pro_number = fields.Char(
        string='PRO Number',
        copy=False,
        readonly=True
    )

    nexterus_bol_url = fields.Char(
        string='Bill of Lading URL',
        copy=False,
        readonly=True
    )

    nexterus_label_url = fields.Char(
        string='Label URL',
        copy=False,
        readonly=True
    )

    nexterus_tracking_url = fields.Char(
        string='Tracking URL',
        copy=False,
        readonly=True
    )