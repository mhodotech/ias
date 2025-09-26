from odoo import models, api, fields
from odoo.exceptions import UserError, ValidationError
import pyodbc
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class GPSyncService(models.Model):
    _name = 'gp.sync.service'
    _description = 'GP Synchronization Service'

    @api.model
    def sync_all_orders(self, config_id=None):
        """Main sync method - can be called from cron or manually"""
        if not config_id:
            config = self.env['gp.config'].search([('active', '=', True)], limit=1)
        else:
            config = self.env['gp.config'].browse(config_id)

        if not config:
            raise UserError('No active GP configuration found')

        log_vals = {
            'name': 'Full Order Sync',
            'gp_config_id': config.id,
            'records_processed': 0,
            'records_created': 0,
            'records_updated': 0,
            'records_failed': 0,
        }

        try:
            conn = pyodbc.connect(config.get_connection_string())
            cursor = conn.cursor()

            # Get orders with picking tickets (ready for Odoo)
            orders_data = self._fetch_orders_with_picking(cursor)

            for order_data in orders_data:
                try:
                    # Fetch order details
                    sopnumbe = order_data['SOPNUMBE']

                    # Get line items
                    line_data = self._fetch_order_lines(cursor, sopnumbe)

                    # Check fulfillment status
                    order_data['has_fulfillment'] = self._check_fulfillment(cursor, sopnumbe)

                    # Get salesperson name
                    order_data['salesperson_name'] = self._get_salesperson_name(
                        cursor, order_data.get('SLPRSNID')
                    )

                    # Get tracking numbers if any
                    order_data['tracking_numbers'] = self._get_tracking_numbers(cursor, sopnumbe)

                    # Create or update in Odoo
                    existing = self.env['sale.order'].search([
                        ('gp_sopnumbe', '=', sopnumbe)
                    ], limit=1)

                    if existing:
                        self.env['sale.order'].update_from_gp(existing, order_data, line_data)
                        log_vals['records_updated'] += 1
                    else:
                        self.env['sale.order'].create_from_gp(order_data, line_data)
                        log_vals['records_created'] += 1

                    log_vals['records_processed'] += 1

                    # Commit every 10 records for better performance
                    if log_vals['records_processed'] % 10 == 0:
                        self.env.cr.commit()

                except Exception as e:
                    _logger.error(f'Error processing order {sopnumbe}: {str(e)}')
                    log_vals['records_failed'] += 1
                    if log_vals.get('error_details'):
                        log_vals['error_details'] += f'\n{sopnumbe}: {str(e)}'
                    else:
                        log_vals['error_details'] = f'{sopnumbe}: {str(e)}'

            cursor.close()
            conn.close()

            log_vals['status'] = 'success' if log_vals['records_failed'] == 0 else 'warning'
            log_vals['message'] = (
                f"Processed {log_vals['records_processed']} orders. "
                f"Created: {log_vals['records_created']}, "
                f"Updated: {log_vals['records_updated']}, "
                f"Failed: {log_vals['records_failed']}"
            )

        except Exception as e:
            log_vals['status'] = 'error'
            log_vals['message'] = f'Sync failed: {str(e)}'
            log_vals['error_details'] = str(e)
            _logger.error(f'GP sync failed: {str(e)}')

        # Create log entry
        self.env['gp.sync.log'].create(log_vals)

        return log_vals

    def _fetch_orders_with_picking(self, cursor):
        """Fetch orders that have picking tickets"""
        query = """
            SELECT 
                SOPNUMBE,
                SOPTYPE,
                DOCDATE,
                CUSTNMBR,
                CUSTNAME,
                CSTPONBR,
                PCKSLPNO,
                BACHNUMB,
                SLPRSNID,
                SALSTERR,
                SUBTOTAL,
                TAXAMNT,
                DOCAMNT,
                ReqShipDate,
                FUFILDAT,
                ACTLSHIP,
                SHIPMTHD,
                FRTAMNT,
                TRDISAMT,
                ShipToName,
                ADDRESS1,
                ADDRESS2,
                ADDRESS3,
                CITY,
                STATE,
                ZIPCODE,
                CNTCPRSN
            FROM SOP10100
            WHERE SOPTYPE = 2
            AND PCKSLPNO IS NOT NULL 
            AND PCKSLPNO != ''
            ORDER BY DOCDATE DESC
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

    def _fetch_order_lines(self, cursor, sopnumbe):
        """Fetch order line items"""
        query = """
            SELECT 
                LNITMSEQ,
                ITEMNMBR,
                ITEMDESC,
                QUANTITY,
                QTYFULFI,
                QTYTBAOR,
                UNITPRCE,
                XTNDPRCE,
                LOCNCODE,
                SOFULFILLMENTBIN,
                ReqShipDate
            FROM SOP10200
            WHERE SOPNUMBE = ?
            AND SOPTYPE = 2
            ORDER BY LNITMSEQ
        """

        cursor.execute(query, sopnumbe)
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

    def _check_fulfillment(self, cursor, sopnumbe):
        """Check if order has fulfillment record"""
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM SOP10106 WHERE SOPNUMBE = ?",
            sopnumbe
        )
        result = cursor.fetchone()
        return result.cnt > 0 if result else False

    def _get_salesperson_name(self, cursor, slprsnid):
        """Get salesperson full name"""
        if not slprsnid:
            return ''

        try:
            cursor.execute(
                "SELECT SLPRSNFN, SPRSNSLN FROM RM00301 WHERE SLPRSNID = ?",
                slprsnid
            )
            result = cursor.fetchone()
            if result:
                return f"{result.SLPRSNFN.strip()} {result.SPRSNSLN.strip()}"
        except:
            pass
        return ''

    def _get_tracking_numbers(self, cursor, sopnumbe):
        """Get tracking numbers for order"""
        tracking = []
        try:
            cursor.execute(
                "SELECT Tracking_Number FROM SOP10107 WHERE SOPNUMBE = ?",
                sopnumbe
            )
            for row in cursor.fetchall():
                if row.Tracking_Number and row.Tracking_Number.strip():
                    tracking.append(row.Tracking_Number.strip())
        except:
            pass
        return tracking

    @api.model
    def sync_specific_order(self, sopnumbe):
        """Sync a specific order by number"""
        config = self.env['gp.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise UserError('No active GP configuration found')

        try:
            conn = pyodbc.connect(config.get_connection_string())
            cursor = conn.cursor()

            # Fetch order
            query = """
                SELECT * FROM SOP10100
                WHERE SOPNUMBE = ? AND SOPTYPE = 2
            """
            cursor.execute(query, sopnumbe)
            columns = [column[0] for column in cursor.description]
            row = cursor.fetchone()

            if not row:
                raise UserError(f'Order {sopnumbe} not found in GP')

            order_data = dict(zip(columns, row))
            # Strip char fields
            for key, value in order_data.items():
                if isinstance(value, str):
                    order_data[key] = value.strip()

            # Get additional data
            line_data = self._fetch_order_lines(cursor, sopnumbe)
            order_data['has_fulfillment'] = self._check_fulfillment(cursor, sopnumbe)
            order_data['salesperson_name'] = self._get_salesperson_name(
                cursor, order_data.get('SLPRSNID')
            )
            order_data['tracking_numbers'] = self._get_tracking_numbers(cursor, sopnumbe)

            cursor.close()
            conn.close()

            # Create or update order
            existing = self.env['sale.order'].search([
                ('gp_sopnumbe', '=', sopnumbe)
            ], limit=1)

            if existing:
                return self.env['sale.order'].update_from_gp(existing, order_data, line_data)
            else:
                return self.env['sale.order'].create_from_gp(order_data, line_data)

        except Exception as e:
            _logger.error(f'Error syncing order {sopnumbe}: {str(e)}')
            raise UserError(f'Sync failed: {str(e)}')

    @api.model
    def sync_all_orders_async(self):
        """Queue the sync_all_orders method for background processing"""
        # Using with_delay() from queue_job v18 - this is the proper way
        self.with_delay(
            channel='gp_sync',
            max_retries=3,
            description='GP Full Order Sync'
        ).sync_all_orders()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'message': 'GP sync job has been queued for background processing',
                'sticky': False,
            }
        }

    @api.model
    def sync_specific_order_async(self, sopnumbe):
        """Queue a specific order sync for background processing"""
        # Using with_delay() from queue_job v18
        self.with_delay(
            channel='gp_sync',
            max_retries=3,
            description=f'GP Sync Order {sopnumbe}'
        ).sync_specific_order(sopnumbe)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'message': f'Order {sopnumbe} sync has been queued',
                'sticky': False,
            }
        }