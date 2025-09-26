from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

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


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def find_or_create_from_gp(self, line_data):
        """Find or create product from GP line data"""
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
                    raise ValidationError(f'Product {item_number} not found and auto-create is disabled')
            else:
                # Create new product
                vals = {
                    'name': line_data.get('ITEMDESC', item_number).strip()[:100],
                    'gp_itemnmbr': item_number,
                    'gp_itemdesc': line_data.get('ITEMDESC', '').strip(),
                    'type': 'consu',
                    'is_storable': True,
                    'sale_ok': True,
                    'purchase_ok': True,
                    'list_price': line_data.get('UNITPRCE', 0),
                }
                product = self.create(vals)
                _logger.info(f'Created new product: {item_number}')

        return product