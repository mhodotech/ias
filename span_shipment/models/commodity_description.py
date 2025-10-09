# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class CommodityDescription(models.Model):
    _name = 'commodity.description'
    _description = 'Commodity Description'
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True
    )

    active = fields.Boolean(
        string='Active',
        default=True
    )