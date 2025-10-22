from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import pyodbc
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class GPProductSync(models.Model):
    _name = 'gp.product.sync'
    _description = 'GP Product Synchronization Service'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Sync Name', default='Product Sync', required=True)
    last_sync_date = fields.Datetime('Last Sync Date', tracking=True)
    sync_status = fields.Selection([
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('error', 'Error')
    ], string='Status', default='idle', tracking=True)

    products_synced = fields.Integer('Products Synced', tracking=True)
    products_created = fields.Integer('Products Created', tracking=True)
    products_updated = fields.Integer('Products Updated', tracking=True)
    error_message = fields.Text('Error Message')

    @api.model
    def sync_all_products(self):
        """Main method to sync all products from GP"""
        config = self.env['gp.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise UserError('No active GP configuration found')

        sync_record = self.create({
            'name': f'Product Sync - {fields.Datetime.now()}',
            'sync_status': 'running',
        })

        try:
            conn = pyodbc.connect(config.get_connection_string())
            cursor = conn.cursor()

            # Fetch all products with their tracking info
            products_data = self._fetch_all_products(cursor)

            created_count = 0
            updated_count = 0

            for product_data in products_data:
                try:
                    itemnmbr = product_data['ITEMNMBR']

                    # Check if product exists
                    existing_product = self.env['product.product'].search([
                        ('gp_itemnmbr', '=', itemnmbr)
                    ], limit=1)

                    if existing_product:
                        self._update_product(existing_product, product_data, cursor, config)
                        updated_count += 1
                    else:
                        self._create_product(product_data, cursor, config)
                        created_count += 1

                    # Commit every 50 records
                    if (created_count + updated_count) % 50 == 0:
                        self.env.cr.commit()

                except Exception as e:
                    _logger.error(f'Error processing product {itemnmbr}: {str(e)}')
                    continue

            cursor.close()
            conn.close()

            sync_record.write({
                'sync_status': 'success',
                'last_sync_date': fields.Datetime.now(),
                'products_synced': len(products_data),
                'products_created': created_count,
                'products_updated': updated_count,
            })

            message = f"Successfully synced {len(products_data)} products. Created: {created_count}, Updated: {updated_count}"
            sync_record.message_post(body=message)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }

        except Exception as e:
            sync_record.write({
                'sync_status': 'error',
                'error_message': str(e),
            })
            _logger.error(f'Product sync failed: {str(e)}')
            raise UserError(f'Sync failed: {str(e)}')

    def _fetch_all_products(self, cursor):
        """Fetch all products from GP"""
        query = """
            SELECT 
                item.ITEMNMBR,
                item.ITEMDESC,
                item.ITMSHNAM,
                item.ITEMTYPE,
                item.ITMCLSCD,
                item.UOMSCHDL,
                item.SELNGUOM,
                item.PRCHSUOM,
                item.ITMTRKOP,  -- 0=None, 1=Serial, 2=Lot
                item.LOTTYPE,   -- 1=Date, 2=Production, 3=Other
                item.CURRCOST,
                item.STNDCOST,
                item.ITEMSHWT,  -- Item shipping weight
                ISNULL(qty.QTYONHND, 0) as QTYONHND,
                ISNULL(qty.ATYALLOC, 0) as ATYALLOC
            FROM IV00101 item
            LEFT JOIN (
                SELECT ITEMNMBR, 
                       SUM(QTYONHND) as QTYONHND, 
                       SUM(ATYALLOC) as ATYALLOC
                FROM IV00102
                GROUP BY ITEMNMBR
            ) qty ON item.ITEMNMBR = qty.ITEMNMBR
            WHERE item.INACTIVE = 0
            ORDER BY item.ITEMNMBR
        """

        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        results = []

        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            # Strip char fields
            for key, value in data.items():
                if isinstance(value, str):
                    data[key] = value.strip()
            results.append(data)

        return results

    def _create_product(self, product_data, cursor, config):
        """Create new product in Odoo"""
        # Determine product type and tracking
        tracking = self._get_tracking_type(product_data['ITMTRKOP'])

        vals = {
            'name': product_data.get('ITEMDESC', product_data['ITEMNMBR']).strip()[:100],
            'default_code': product_data['ITEMNMBR'],
            'gp_itemnmbr': product_data['ITEMNMBR'],
            'gp_itemdesc': product_data.get('ITEMDESC', '').strip(),
            'gp_itmclscd': product_data.get('ITMCLSCD', '').strip(),
            'type': 'consu',  # Odoo 18 uses consu instead of product
            'is_storable': True,  # New in Odoo 18
            'tracking': tracking,  # 'none', 'lot', 'serial'
            'sale_ok': True,
            'purchase_ok': True,
            'standard_price': float(product_data.get('STNDCOST', 0) or 0),
            'list_price': product_data.get('CURRCOST', 0),
        }

        # Add weight if available (from span_shipment module fields)
        if product_data.get('ITEMSHWT'):
            vals['weight'] = float(product_data.get('ITEMSHWT', 0))

        # Try to determine NMFC class based on item class or other logic
        # This is where you could add custom logic to map GP item classes to NMFC
        if product_data.get('ITMCLSCD'):
            vals['gp_itmclscd'] = str(product_data['ITMCLSCD']).strip()
            # You can add mapping logic here if needed
            # For example:
            # nmfc_class = self._get_nmfc_class_from_gp(product_data['ITMCLSCD'])
            # if nmfc_class:
            #     vals['nmfc_class'] = nmfc_class

        product = self.env['product.product'].create(vals)

        # Create initial stock if exists
        if product_data.get('QTYONHND', 0) > 0 and config.default_location_id:
            self._create_initial_stock(product, product_data, cursor, config)

        # Import lots/serials if applicable
        if tracking != 'none':
            self._import_tracking_info(product, cursor, config)

        _logger.info(f'Created product: {product_data["ITEMNMBR"]}')
        return product

    def _update_product(self, product, product_data, cursor, config):
        """Update existing product"""
        tracking = self._get_tracking_type(product_data['ITMTRKOP'])

        vals = {
            'gp_itemdesc': product_data.get('ITEMDESC', '').strip(),
            'gp_itmclscd': product_data.get('ITMCLSCD', '').strip(),
            'tracking': tracking,
            'standard_price': float(product_data.get('STNDCOST', 0) or 0),
        }

        # Update weight if changed
        if product_data.get('ITEMSHWT') is not None:
            new_weight = float(product_data.get('ITEMSHWT', 0))
            if abs((product.weight or 0) - new_weight) > 0.01:
                vals['weight'] = new_weight

        # Only update name if it's significantly different
        new_name = product_data.get('ITEMDESC', product_data['ITEMNMBR']).strip()[:100]
        if new_name and new_name != product.name and len(new_name) > 3:
            vals['name'] = new_name

        product.write(vals)

        # Update stock quantities
        self._update_stock_quantities(product, product_data, cursor, config)

        # Update lots/serials if applicable
        if tracking != 'none':
            self._import_tracking_info(product, cursor, config)

        _logger.info(f'Updated product: {product_data["ITEMNMBR"]}')

    def _get_tracking_type(self, itmtrkop):
        """Convert GP tracking type to Odoo tracking"""
        if itmtrkop == 1:
            return 'serial'
        elif itmtrkop == 2:
            return 'lot'
        else:
            return 'none'

    def _create_initial_stock(self, product, product_data, cursor, config):
        """Create initial stock for new product"""
        location = config.default_location_id
        if not location:
            location = self.env['stock.location'].search([
                ('usage', '=', 'internal'),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

        if not location:
            return

        # Create stock quant for non-tracked items
        if product.tracking == 'none':
            qty_on_hand = float(product_data.get('QTYONHND', 0) or 0)
            if qty_on_hand > 0:
                self.env['stock.quant'].create({
                    'product_id': product.id,
                    'location_id': location.id,
                    'quantity': qty_on_hand,
                })

    def _update_stock_quantities(self, product, product_data, cursor, config):
        """Update stock quantities for existing product"""
        # For now, we'll just log the difference
        # In production, you might want to create inventory adjustments

        current_qty = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id.usage', '=', 'internal')
        ]).mapped('quantity')

        current_total = sum(current_qty)
        gp_total = product_data.get('QTYONHND', 0)

        if abs(current_total - gp_total) > 0.01:
            _logger.info(f'Quantity mismatch for {product.default_code}: Odoo={current_total}, GP={gp_total}')
            # You can create an inventory adjustment here if needed

    def _import_tracking_info(self, product, cursor, config):
        """Import lot or serial numbers for a product"""
        if product.tracking == 'lot':
            self._import_lots(product, cursor, config)
        elif product.tracking == 'serial':
            self._import_serials(product, cursor, config)

    def _import_lots(self, product, cursor, config):
        """Import lot numbers from GP"""
        query = """
            SELECT 
                LOTNUMBR,
                LOCNCODE,
                QTYRECVD,
                QTYSOLD,
                ATYALLOC,
                MFGDATE,
                EXPNDATE
            FROM IV00300
            WHERE ITEMNMBR = ?
            AND (QTYRECVD - QTYSOLD) > 0
            ORDER BY LOTNUMBR
        """

        cursor.execute(query, product.gp_itemnmbr)

        location = config.default_location_id or self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        for row in cursor.fetchall():
            lot_number = row.LOTNUMBR.strip()
            qty_on_hand = row.QTYRECVD - row.QTYSOLD

            if qty_on_hand <= 0:
                continue

            # Check if lot exists
            lot = self.env['stock.lot'].search([
                ('name', '=', lot_number),
                ('product_id', '=', product.id),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

            if not lot:
                lot_vals = {
                    'name': lot_number,
                    'product_id': product.id,
                    'company_id': self.env.company.id,
                }

                if row.EXPNDATE and row.EXPNDATE != '1900-01-01':
                    try:
                        lot_vals['expiration_date'] = row.EXPNDATE
                    except:
                        pass

                lot = self.env['stock.lot'].create(lot_vals)

            # Update or create quant
            quant = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('lot_id', '=', lot.id),
                ('location_id', '=', location.id)
            ], limit=1)

            if quant:
                if abs(quant.quantity - qty_on_hand) > 0.01:
                    quant.quantity = qty_on_hand
            else:
                self.env['stock.quant'].create({
                    'product_id': product.id,
                    'lot_id': lot.id,
                    'location_id': location.id,
                    'quantity': qty_on_hand,
                })

    def _import_serials(self, product, cursor, config):
        """Import serial numbers from GP"""
        query = """
            SELECT 
                SERLNMBR,
                LOCNCODE,
                UNITCOST,
                SERLNSLD
            FROM IV00200
            WHERE ITEMNMBR = ?
            AND SERLNSLD = 0  -- Only available serials
            ORDER BY SERLNMBR
        """

        cursor.execute(query, product.gp_itemnmbr)

        location = config.default_location_id or self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        for row in cursor.fetchall():
            serial_number = row.SERLNMBR.strip()

            # Check if serial exists
            lot = self.env['stock.lot'].search([
                ('name', '=', serial_number),
                ('product_id', '=', product.id),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

            if not lot:
                lot = self.env['stock.lot'].create({
                    'name': serial_number,
                    'product_id': product.id,
                    'company_id': self.env.company.id,
                })

            # Check if quant exists
            quant = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('lot_id', '=', lot.id),
                ('location_id', '=', location.id)
            ], limit=1)

            if not quant:
                self.env['stock.quant'].create({
                    'product_id': product.id,
                    'lot_id': lot.id,
                    'location_id': location.id,
                    'quantity': 1.0,  # Serial numbers always have qty 1
                })

    @api.model
    def action_open_sync_wizard(self):
        """Open the sync wizard"""
        return {
            'name': 'Sync Products from GP',
            'type': 'ir.actions.act_window',
            'res_model': 'gp.product.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
        }