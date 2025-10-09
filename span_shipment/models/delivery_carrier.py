# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('nexterus', 'Nexterus LTL')],
        ondelete={'nexterus': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})}
    )

    # Nexterus configuration
    nexterus_username = fields.Char(
        string='Nexterus Username'
    )
    nexterus_password = fields.Char(
        string='Nexterus Password'
    )
    nexterus_scac = fields.Char(
        string='SCAC Code',
        help='Standard Carrier Alpha Code'
    )

    # Timing configuration
    nexterus_close_time = fields.Float(
        string='Close Time',
        default=19.0,
        help='Time when shipping closes (24-hour format)'
    )
    nexterus_ready_time = fields.Float(
        string='Ready Time',
        default=17.0,
        help='Time when freight is ready (24-hour format)'
    )
    nexterus_rate_expiration = fields.Integer(
        string='Rate Expiration (hours)',
        default=24,
        help='Hours until rates expire'
    )

    # Default freight class
    nexterus_default_freight_class = fields.Selection([
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
    ], string='Default Freight Class', default='85')

    # Carrier type for filtering
    is_ltl = fields.Boolean(
        string='LTL Carrier',
        compute='_compute_is_ltl',
        store=True
    )

    @api.depends('delivery_type')
    def _compute_is_ltl(self):
        for carrier in self:
            carrier.is_ltl = carrier.delivery_type == 'nexterus'