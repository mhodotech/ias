from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class GPSyncLog(models.Model):
    _name = 'gp.sync.log'
    _description = 'GP Sync Log'
    _order = 'create_date desc'

    name = fields.Char('Operation', required=True)
    status = fields.Selection([
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], string='Status', required=True)
    message = fields.Text('Message')
    gp_config_id = fields.Many2one('gp.config', 'Configuration')
    records_processed = fields.Integer('Records Processed')
    records_created = fields.Integer('Records Created')
    records_updated = fields.Integer('Records Updated')
    records_failed = fields.Integer('Records Failed')
    error_details = fields.Text('Error Details')