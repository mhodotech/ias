# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import re


class CarrierCloseConfig(models.Model):
    _name = 'carrier.close.config'
    _description = 'Carrier Close Email Configuration'
    _order = 'email'
    _rec_name = 'email'

    email = fields.Char(
        string='Email Address',
        required=True,
        help='Email address to receive carrier close notifications'
    )

    name = fields.Char(
        string='Contact Name',
        help='Name of the person receiving notifications'
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this email will not receive notifications'
    )

    notes = fields.Text(
        string='Notes',
        help='Additional notes about this recipient'
    )

    @api.constrains('email')
    def _check_email(self):
        """Validate email format"""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for record in self:
            if record.email and not re.match(email_pattern, record.email):
                raise ValidationError(_('Invalid email format: %s') % record.email)

    _sql_constraints = [
        ('email_unique', 'UNIQUE(email)', 'This email address is already configured!'),
    ]