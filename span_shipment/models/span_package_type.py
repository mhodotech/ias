# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SpanPackageType(models.Model):
    _name = 'span.package.type'
    _description = 'Span Package Type'
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True
    )
    code = fields.Char(
        string='Code',
        required=True,
        help='Code to send to carriers (e.g., PKG, CASE)'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    notes = fields.Text(
        string='Notes'
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Code must be unique!'),
    ]