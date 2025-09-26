from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class GPSyncWizard(models.TransientModel):
    _name = 'gp.sync.wizard'
    _description = 'GP Sync Wizard'

    sync_type = fields.Selection([
        ('all', 'All Orders with Picking Tickets'),
        ('specific', 'Specific Order'),
        ('date_range', 'Date Range'),
    ], string='Sync Type', default='all', required=True)

    sopnumbe = fields.Char('GP Order Number')
    date_from = fields.Date('From Date')
    date_to = fields.Date('To Date')

    use_queue = fields.Boolean(
        'Use Background Queue',
        default=True,  # Default to True since queue_job is available
        help='Process sync in background using queue jobs'
    )

    @api.onchange('sync_type')
    def _onchange_sync_type(self):
        if self.sync_type != 'specific':
            self.sopnumbe = False
        if self.sync_type != 'date_range':
            self.date_from = False
            self.date_to = False

    def action_sync(self):
        """Execute synchronization"""
        self.ensure_one()

        sync_service = self.env['gp.sync.service']

        if self.sync_type == 'specific':
            if not self.sopnumbe:
                raise UserError('Please enter a GP order number')

            sopnumbe = self.sopnumbe.strip()

            if self.use_queue:
                # Use the async method that properly uses with_delay()
                sync_service.sync_specific_order_async(sopnumbe)
                message = f'Sync job for order {sopnumbe} has been queued'
            else:
                # Direct execution
                order = sync_service.sync_specific_order(sopnumbe)
                message = f'Order {order.name} synchronized successfully'

        elif self.sync_type == 'date_range':
            if not self.date_from or not self.date_to:
                raise UserError('Please select date range')

            # Date range sync would need implementation
            raise UserError('Date range sync not yet implemented')

        else:  # all
            if self.use_queue:
                # Use the async method that properly uses with_delay()
                sync_service.sync_all_orders_async()
                message = 'Full sync job has been queued in background'
            else:
                # Direct execution
                result = sync_service.sync_all_orders()
                message = result.get('message', 'Sync completed')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': message,
                'sticky': False,
            }
        }