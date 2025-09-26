from odoo import models, fields, api
import logging
import pyodbc
from datetime import datetime

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    gp_pckslpno = fields.Char(
        'GP Picking Ticket',
        index=True,
        help='Picking ticket number from GP'
    )
    gp_bachnumb = fields.Char(
        'GP Batch Number',
        help='Batch number from GP'
    )
    gp_ship_status_updated = fields.Boolean(
        'GP Ship Status Updated',
        default=False,
        help='Flag to track if GP has been notified of shipment'
    )
    gp_ship_update_date = fields.Datetime(
        'GP Ship Update Date',
        help='Date when GP was notified of shipment'
    )

    def button_validate(self):
        """Override to notify GP when delivery order is validated"""
        res = super().button_validate()

        # Check for delivery orders that need GP update
        for picking in self:
            if picking.picking_type_id.code == 'outgoing' and picking.sale_id and picking.sale_id.gp_sopnumbe:
                # This is a delivery order linked to a GP sales order
                picking.update_gp_shipment_status()

        return res

    def update_gp_shipment_status(self):
        """Update GP with shipment status when delivery is validated"""
        self.ensure_one()

        if not self.sale_id or not self.sale_id.gp_sopnumbe:
            return False

        try:
            # Get GP config
            config = self.env['gp.config'].search([('active', '=', True)], limit=1)
            if not config:
                _logger.warning('No active GP configuration found for shipment update')
                return False

            # Prepare shipment data for API
            shipment_data = self._prepare_shipment_data()

            # Store the shipment data in a table for GP team to consume
            self.env['gp.shipment.notification'].create(shipment_data)

            # Mark as updated
            self.write({
                'gp_ship_status_updated': True,
                'gp_ship_update_date': fields.Datetime.now()
            })

            _logger.info(f'Created shipment notification for GP order {self.sale_id.gp_sopnumbe}')
            return True

        except Exception as e:
            _logger.error(f'Error updating GP shipment status: {str(e)}')
            return False

    def _prepare_shipment_data(self):
        """Prepare shipment data for GP API"""
        self.ensure_one()

        # Collect tracking numbers if any
        tracking_numbers = []
        if self.carrier_tracking_ref:
            tracking_numbers.append(self.carrier_tracking_ref)

        # Prepare line items with shipped quantities
        line_items = []
        for move in self.move_ids:
            if move.product_id.gp_itemnmbr:
                # In Odoo 18, quantity_done is on move_line_ids, not on move
                qty_done = sum(move.move_line_ids.mapped('qty_done'))
                line_items.append({
                    'item_number': move.product_id.gp_itemnmbr,
                    'quantity_shipped': qty_done,  # Fixed: use qty_done from move lines
                    'lot_number': ','.join(move.move_line_ids.mapped('lot_id.name')) if move.move_line_ids else '',
                })

        return {
            'gp_sopnumbe': self.sale_id.gp_sopnumbe,
            'odoo_delivery_name': self.name,
            'ship_date': fields.Datetime.now(),
            'tracking_numbers': ','.join(tracking_numbers) if tracking_numbers else '',
            'carrier_name': self.carrier_id.name if self.carrier_id else '',
            'status': 'shipped',
            'ready_for_invoice': True,
            'line_items': str(line_items),  # Store as JSON string
            'processed': False,
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    gp_bin_location = fields.Char(
        'GP Bin Location',
        help='Bin location from GP (SOFULFILLMENTBIN)'
    )