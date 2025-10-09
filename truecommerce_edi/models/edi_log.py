from odoo import models, fields, api


class EDILog(models.Model):
    _name = 'edi.log'
    _description = 'EDI Generation Log'
    _order = 'create_date desc'
    _rec_name = 'file_name'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        ondelete='cascade'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='picking_id.partner_id',
        store=True
    )
    file_name = fields.Char(
        'File Name',
        required=True
    )
    file_path = fields.Char(
        'File Path'
    )
    file_content = fields.Text(
        'File Content',
        help='EDI file content for reference'
    )
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], string='Status', required=True, default='success')
    error_message = fields.Text(
        'Error Message'
    )
    control_number = fields.Char(
        'Control Number',
        help='ISA control number used'
    )
    transaction_count = fields.Integer(
        'Transaction Count',
        help='Number of transactions in the file'
    )