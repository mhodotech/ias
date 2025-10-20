# -*- coding: utf-8 -*-
from odoo import fields, models, api, _


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

    third_party_freight_billing = fields.Boolean(
        string='Be billed for third party freight charges',
        help='Check if this partner should be billed for third party freight charges'
    )

    @api.constrains('third_party_freight_billing')
    def _check_single_freight_billing(self):
        """Ensure only one partner has freight billing checked"""
        for partner in self:
            if partner.third_party_freight_billing:
                other_partners = self.search([
                    ('third_party_freight_billing', '=', True),
                    ('id', '!=', partner.id)
                ])
                if other_partners:
                    raise ValidationError(_('Only one partner can be marked for third party freight billing.'))