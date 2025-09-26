from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class GPIntegrationAPI(http.Controller):

    @http.route('/api/gp/shipment_notifications', type='json', auth='public', methods=['POST'], csrf=False)
    def get_shipment_notifications(self, **kwargs):
        """
        API endpoint for GP to fetch pending shipment notifications
        Returns list of pending notifications with shipment details
        """
        try:
            # Check API key from headers
            api_key = request.httprequest.headers.get('X-API-KEY')
            if not api_key:
                return {'status': 'error', 'message': 'API key required'}

            # Validate API key (you'll need to implement this validation)
            # For now, let's just check if it exists

            limit = kwargs.get('limit', 100)
            notifications = request.env['gp.shipment.notification'].sudo().get_pending_notifications(limit=limit)

            return {
                'status': 'success',
                'data': notifications,
                'count': len(notifications)
            }
        except Exception as e:
            _logger.error(f'Error in get_shipment_notifications: {str(e)}')
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/api/gp/mark_processed', type='json', auth='public', methods=['POST'], csrf=False)
    def mark_notification_processed(self, **kwargs):
        """
        API endpoint for GP to mark a notification as processed
        """
        try:
            # Check API key
            api_key = request.httprequest.headers.get('X-API-KEY')
            if not api_key:
                return {'status': 'error', 'message': 'API key required'}

            notification_id = kwargs.get('notification_id')
            error_message = kwargs.get('error_message')

            if not notification_id:
                return {'status': 'error', 'message': 'notification_id required'}

            success = request.env['gp.shipment.notification'].sudo().mark_as_processed(
                notification_id,
                error_message=error_message
            )

            if success:
                return {
                    'status': 'success',
                    'message': f'Notification {notification_id} marked as processed'
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Notification {notification_id} not found'
                }
        except Exception as e:
            _logger.error(f'Error in mark_notification_processed: {str(e)}')
            return {
                'status': 'error',
                'message': str(e)
            }