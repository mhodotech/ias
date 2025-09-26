# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CarrierRates(models.TransientModel):
    _name = 'carrier.rates'
    _description = 'Carrier Rates'

    wizard_id = fields.Many2one('choose.delivery.carrier', string='Wizard')
    choose = fields.Boolean('Select')
    carrier_scac = fields.Char('SCAC')
    name = fields.Char('Carrier Name')
    price = fields.Monetary('Rate')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.user.company_id.currency_id.id,  # Better default
    )
    service = fields.Char('Transit Time')
    service_id = fields.Char('Service ID')
    estimated_delivery_date = fields.Char('Est. Delivery')
    carrier_id = fields.Many2one('delivery.carrier', string='Carrier')