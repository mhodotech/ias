from odoo import models, fields, api


class EDIPartnerConfig(models.Model):
    _name = 'edi.partner.config'
    _description = 'EDI Partner Configuration'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        ondelete='cascade'
    )

    # EDI Identifiers
    edi_id = fields.Char(
        'EDI ID',
        required=True,
        help='Partner EDI identification number'
    )
    edi_id_qualifier = fields.Selection([
        ('01', 'Duns'),
        ('12', 'Phone'),
        ('14', 'Duns Plus Suffix'),
        ('ZZ', 'Mutually Defined'),
        ('92', 'Assigned by Buyer'),
    ], string='EDI ID Qualifier', default='ZZ', required=True)

    location_code = fields.Char(
        'Location Code',
        help='Ship-to location code if different from main'
    )

    # Document Options
    include_pack_level = fields.Boolean(
        'Include Pack Level',
        default=True,
        help='Include package/carton level in hierarchy'
    )
    include_item_serial = fields.Boolean(
        'Include Item Serial Numbers',
        default=True,
        help='Include serial numbers at item level'
    )
    use_customer_item_number = fields.Boolean(
        'Use Customer Item Number',
        default=False,
        help='Use customer part number instead of internal'
    )

    # Special Requirements
    special_qualifier = fields.Char(
        'Special Qualifier',
        help='Any special qualifier codes required by this partner'
    )
    notes = fields.Text(
        'EDI Notes',
        help='Special EDI requirements or notes for this partner'
    )

    active = fields.Boolean('Active', default=True)

    _sql_constraints = [
        ('partner_uniq', 'UNIQUE(partner_id)', 'EDI configuration already exists for this partner!'),
    ]
