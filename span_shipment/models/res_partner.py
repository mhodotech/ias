# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Default shipping requirements
    default_requires_liftgate = fields.Boolean(
        string='Default Liftgate Service',
        help='Default to requiring liftgate for deliveries to this partner'
    )
    default_requires_inside_delivery = fields.Boolean(
        string='Default Inside Delivery',
        help='Default to requiring inside delivery for this partner'
    )