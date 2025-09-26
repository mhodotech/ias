from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class GPShipmentNotification(models.Model):
    _name = 'gp.shipment.notification'
    _description = 'GP Shipment Notifications'
    _order = 'create_date desc'
    _rec_name = 'gp_sopnumbe'

    gp_sopnumbe = fields.Char(
        'GP Order Number',
        required=True,
        index=True,
        help='SOPNUMBE from GP'
    )
    odoo_delivery_name = fields.Char(
        'Odoo Delivery Name',
        required=True,
        help='Name of the delivery order in Odoo'
    )
    ship_date = fields.Datetime(
        'Ship Date',
        required=True,
        help='Date when shipment was validated'
    )
    tracking_numbers = fields.Text(
        'Tracking Numbers',
        help='Comma-separated tracking numbers'
    )
    carrier_name = fields.Char(
        'Carrier Name',
        help='Name of the shipping carrier'
    )
    status = fields.Selection([
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
    ], string='Status', default='shipped', required=True)
    ready_for_invoice = fields.Boolean(
        'Ready for Invoice',
        default=True,
        help='Flag indicating order is ready for invoicing in GP'
    )
    line_items = fields.Text(
        'Line Items',
        help='JSON string of shipped line items'
    )
    processed = fields.Boolean(
        'Processed by GP',
        default=False,
        help='Flag to indicate if GP has processed this notification'
    )
    processed_date = fields.Datetime(
        'Processed Date',
        help='Date when GP processed this notification'
    )
    error_message = fields.Text(
        'Error Message',
        help='Any error message from GP processing'
    )

    @api.model
    def get_pending_notifications(self, limit=100):
        """API method for GP to fetch pending notifications"""
        notifications = self.search([('processed', '=', False)], limit=limit)
        result = []

        for notification in notifications:
            data = {
                'id': notification.id,
                'gp_sopnumbe': notification.gp_sopnumbe,
                'ship_date': notification.ship_date.isoformat() if notification.ship_date else None,
                'tracking_numbers': notification.tracking_numbers.split(',') if notification.tracking_numbers else [],
                'carrier_name': notification.carrier_name or '',
                'status': notification.status,
                'ready_for_invoice': notification.ready_for_invoice,
            }

            # Parse line items if present
            if notification.line_items:
                try:
                    data['line_items'] = eval(notification.line_items)  # Convert string back to list
                except:
                    data['line_items'] = []
            else:
                data['line_items'] = []

            result.append(data)

        return result

    @api.model
    def mark_as_processed(self, notification_id, error_message=None):
        """API method for GP to mark notification as processed"""
        notification = self.browse(notification_id)
        if notification.exists():
            vals = {
                'processed': True,
                'processed_date': fields.Datetime.now()
            }
            if error_message:
                vals['error_message'] = error_message
            notification.write(vals)
            return True
        return False