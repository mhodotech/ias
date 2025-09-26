from odoo import models, fields, api
from odoo.exceptions import ValidationError
import pyodbc
import logging

_logger = logging.getLogger(__name__)


class GPConfig(models.Model):
    _name = 'gp.config'
    _description = 'GP Database Configuration'
    _rec_name = 'name'

    name = fields.Char('Configuration Name', required=True)
    server = fields.Char('Server', required=True, default='s-spod-sql03')
    database = fields.Char('Database', required=True, default='TEST')
    username = fields.Char('Username', required=True)
    password = fields.Char('Password', required=True)
    port = fields.Integer('Port', default=1433)
    tds_version = fields.Selection([
        ('7.4', 'TDS 7.4'),
        ('8.0', 'TDS 8.0'),
    ], string='TDS Version', default='7.4')
    active = fields.Boolean('Active', default=True)

    # Sync settings
    auto_create_products = fields.Boolean(
        'Auto Create Products',
        default=True,
        help='Automatically create products if not found in Odoo'
    )
    auto_create_customers = fields.Boolean(
        'Auto Create Customers',
        default=True,
        help='Automatically create customers if not found in Odoo'
    )
    default_location_id = fields.Many2one(
        'stock.location',
        'Default Stock Location',
        domain=[('usage', '=', 'internal')]
    )

    @api.constrains('active')
    def _check_single_active(self):
        if self.active and self.search_count([('active', '=', True)]) > 1:
            raise ValidationError('Only one configuration can be active at a time')

    def get_connection_string(self):
        """Build pyodbc connection string"""
        self.ensure_one()
        return (
            f'DRIVER={{FreeTDS}};'
            f'SERVER={self.server};'
            f'PORT={self.port};'
            f'DATABASE={self.database};'
            f'UID={self.username};'
            f'PWD={self.password};'
            f'TDS_Version={self.tds_version}'
        )

    def test_connection(self):
        """Test GP database connection"""
        self.ensure_one()
        try:
            conn_str = self.get_connection_string()
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            # Test query
            cursor.execute("SELECT COUNT(*) FROM SOP10100 WHERE SOPTYPE = 2")
            count = cursor.fetchone()[0]

            cursor.close()
            conn.close()

            message = f'Connection successful! Found {count} active orders in GP.'
            self.env['gp.sync.log'].create({
                'name': 'Connection Test',
                'status': 'success',
                'message': message,
                'gp_config_id': self.id,
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': message,
                    'sticky': False,
                }
            }

        except Exception as e:
            self.env['gp.sync.log'].create({
                'name': 'Connection Test',
                'status': 'error',
                'message': str(e),
                'gp_config_id': self.id,
            })
            raise ValidationError(f'Connection failed: {str(e)}')
