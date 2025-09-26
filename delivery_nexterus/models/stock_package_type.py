from odoo import fields, models


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    # Check if the field exists and how it's defined
    # If it has a non-list selection, we need to redefine it
    # Otherwise we can use selection_add

    package_carrier_type = fields.Selection(
        selection=[
            ('none', 'No carrier integration'),
            ('nexterus', 'Nexterus'),
        ],
        string='Carrier Integration Type',
        default='none',
        help='Type of carrier integration for this package'
    )