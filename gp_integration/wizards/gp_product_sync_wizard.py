from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class GPProductSyncWizard(models.TransientModel):
    _name = 'gp.product.sync.wizard'
    _description = 'GP Product Sync Wizard'

    sync_mode = fields.Selection([
        ('all', 'All Products'),
        ('new', 'New Products Only'),
        ('existing', 'Update Existing Only'),
        ('specific', 'Specific Product'),
    ], string='Sync Mode', default='all', required=True)

    specific_itemnmbr = fields.Char(
        'GP Item Number',
        help='Enter GP item number for specific sync'
    )

    sync_inventory = fields.Boolean(
        'Sync Inventory Quantities',
        default=True,
        help='Import current stock levels from GP'
    )

    sync_lots_serials = fields.Boolean(
        'Sync Lot/Serial Numbers',
        default=True,
        help='Import lot and serial numbers from GP'
    )

    create_adjustments = fields.Boolean(
        'Create Inventory Adjustments',
        default=False,
        help='Create inventory adjustments for quantity differences'
    )

    use_queue = fields.Boolean(
        'Use Background Queue',
        default=True,
        help='Process sync in background using queue jobs'
    )

    @api.onchange('sync_mode')
    def _onchange_sync_mode(self):
        if self.sync_mode != 'specific':
            self.specific_itemnmbr = False

    def action_sync(self):
        """Execute product synchronization"""
        self.ensure_one()

        if self.sync_mode == 'specific' and not self.specific_itemnmbr:
            raise UserError('Please enter a GP item number for specific sync')

        sync_service = self.env['gp.product.sync']

        if self.use_queue:
            # Queue the sync job
            sync_service.with_delay(
                channel='gp_sync',
                max_retries=3,
                description=f'GP Product Sync - {self.sync_mode}'
            ).sync_all_products()

            message = 'Product sync job has been queued in background'
        else:
            # Direct execution
            sync_service.sync_all_products()
            message = 'Product sync completed successfully'

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

    def action_sync_and_view(self):
        """Sync and then view the sync log"""
        self.ensure_one()

        # Perform sync
        sync_service = self.env['gp.product.sync']
        sync_record = sync_service.sync_all_products()

        # Open the sync record
        return {
            'name': 'Product Sync Result',
            'type': 'ir.actions.act_window',
            'res_model': 'gp.product.sync',
            'res_id': sync_record.id if isinstance(sync_record, models.Model) else False,
            'view_mode': 'form',
            'target': 'current',
        }