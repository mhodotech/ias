from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Existing GP fields
    gp_itemnmbr = fields.Char(
        'GP Item Number',
        index=True,
        help='Item number from GP (ITEMNMBR)'
    )
    gp_itemdesc = fields.Text(
        'GP Item Description',
        help='Original item description from GP'
    )
    gp_itmclscd = fields.Char(
        'GP Item Class',
        help='Item class code from GP'
    )

    # New GP tracking fields
    gp_itmtrkop = fields.Selection([
        ('0', 'None'),
        ('1', 'Serial'),
        ('2', 'Lot')
    ], string='GP Tracking Type', help='Tracking type from GP')

    gp_last_sync = fields.Datetime(
        'Last GP Sync',
        help='Last synchronization with GP'
    )

    # Odoo 18 specific - Override type field behavior
    is_storable = fields.Boolean(
        'Is Storable Product',
        default=True,
        help='Indicates if this product can be stocked'
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override to set proper product type for GP imports"""
        for vals in vals_list:
            # If coming from GP, ensure it's set as storable consumable
            if vals.get('gp_itemnmbr'):
                vals['type'] = 'consu'  # Odoo 18 uses consu
                vals['is_storable'] = True
        return super().create(vals_list)

    def sync_from_gp(self):
        """Action to sync this specific product from GP"""
        self.ensure_one()

        # Delegate to product.product model
        product = self.env['product.product'].search([
            ('product_tmpl_id', '=', self.id)
        ], limit=1)

        if product:
            return product.sync_from_gp()
        else:
            raise ValidationError('No product variant found for this template')

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def find_or_create_from_gp(self, line_data):
        """Enhanced to handle tracking information"""
        item_number = line_data.get('ITEMNMBR', '').strip()

        # Search existing product
        product = self.search([('gp_itemnmbr', '=', item_number)], limit=1)

        if not product:
            # Check if auto-create is enabled
            config = self.env['gp.config'].search([('active', '=', True)], limit=1)
            if not config or not config.auto_create_products:
                # Try to find by name as fallback
                product = self.search([('name', '=', item_number)], limit=1)
                if not product:
                    # Try to sync this specific product from GP
                    self._sync_single_product_from_gp(item_number, config)
                    # Try to find again after sync
                    product = self.search([('gp_itemnmbr', '=', item_number)], limit=1)

                    if not product:
                        raise ValidationError(f'Product {item_number} not found and auto-create is disabled')
            else:
                # Create new product with basic info
                vals = {
                    'name': line_data.get('ITEMDESC', item_number).strip()[:100],
                    'gp_itemnmbr': item_number,
                    'gp_itemdesc': line_data.get('ITEMDESC', '').strip(),
                    'type': 'consu',  # Odoo 18
                    'is_storable': True,
                    'sale_ok': True,
                    'purchase_ok': True,
                    'list_price': line_data.get('UNITPRCE', 0),
                    'tracking': 'none',  # Will be updated by sync
                }
                product = self.create(vals)
                _logger.info(f'Created new product: {item_number}')

        return product

    @api.model
    def _sync_single_product_from_gp(self, item_number, config=None):
        """Sync a single product from GP"""
        if not config:
            config = self.env['gp.config'].search([('active', '=', True)], limit=1)

        if not config:
            return False

        try:
            import pyodbc
            conn = pyodbc.connect(config.get_connection_string())
            cursor = conn.cursor()

            # Fetch product data
            query = """
                SELECT 
                    item.ITEMNMBR,
                    item.ITEMDESC,
                    item.ITMCLSCD,
                    item.ITMTRKOP,
                    item.CURRCOST,
                    item.STNDCOST
                FROM IV00101 item
                WHERE item.ITEMNMBR = ?
            """

            cursor.execute(query, item_number)
            row = cursor.fetchone()

            if row:
                tracking = 'none'
                if row.ITMTRKOP == 1:
                    tracking = 'serial'
                elif row.ITMTRKOP == 2:
                    tracking = 'lot'

                vals = {
                    'name': (row.ITEMDESC or item_number).strip()[:100],
                    'default_code': item_number.strip(),
                    'gp_itemnmbr': item_number.strip(),
                    'gp_itemdesc': (row.ITEMDESC or '').strip(),
                    'gp_itmclscd': (row.ITMCLSCD or '').strip(),
                    'gp_itmtrkop': str(row.ITMTRKOP),
                    'type': 'consu',
                    'is_storable': True,
                    'tracking': tracking,
                    'sale_ok': True,
                    'purchase_ok': True,
                    'standard_price': row.STNDCOST or 0,
                    'list_price': row.CURRCOST or 0,
                    'gp_last_sync': fields.Datetime.now(),
                }

                product = self.create(vals)
                _logger.info(f'Synced product from GP: {item_number}')

                cursor.close()
                conn.close()
                return product

            cursor.close()
            conn.close()

        except Exception as e:
            _logger.error(f'Error syncing product {item_number} from GP: {str(e)}')

        return False

    def sync_from_gp(self):
        """Action to sync this specific product from GP"""
        self.ensure_one()

        if not self.gp_itemnmbr:
            raise ValidationError('This product does not have a GP item number')

        config = self.env['gp.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise ValidationError('No active GP configuration found')

        try:
            import pyodbc
            conn = pyodbc.connect(config.get_connection_string())
            cursor = conn.cursor()

            # Get sync service
            sync_service = self.env['gp.product.sync']

            # Fetch fresh data from GP
            query = """
                SELECT 
                    item.*,
                    ISNULL(qty.QTYONHND, 0) as QTYONHND
                FROM IV00101 item
                LEFT JOIN (
                    SELECT ITEMNMBR, SUM(QTYONHND) as QTYONHND
                    FROM IV00102
                    GROUP BY ITEMNMBR
                ) qty ON item.ITEMNMBR = qty.ITEMNMBR
                WHERE item.ITEMNMBR = ?
            """

            cursor.execute(query, self.gp_itemnmbr)
            columns = [column[0] for column in cursor.description]
            row = cursor.fetchone()

            if row:
                product_data = dict(zip(columns, row))
                # Strip char fields
                for key, value in product_data.items():
                    if isinstance(value, str):
                        product_data[key] = value.strip()

                # Update product
                sync_service._update_product(self, product_data, cursor, config)

                message = f'Product {self.gp_itemnmbr} synced successfully from GP'
            else:
                message = f'Product {self.gp_itemnmbr} not found in GP'

            cursor.close()
            conn.close()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Complete',
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            raise UserError(f'Error syncing from GP: {str(e)}')