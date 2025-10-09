from odoo import models, fields, api
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    edi_file_generated = fields.Boolean(
        'EDI File Generated',
        default=False,
        copy=False,
        help='Indicates if EDI 856 file has been generated for this delivery'
    )
    edi_file_name = fields.Char(
        'EDI File Name',
        copy=False,
        help='Name of the generated EDI file'
    )
    edi_generation_date = fields.Datetime(
        'EDI Generation Date',
        copy=False,
        help='Date when EDI file was generated'
    )
    edi_log_ids = fields.One2many(
        'edi.log',
        'picking_id',
        string='EDI Logs'
    )
    edi_log_count = fields.Integer(
        'EDI Log Count',
        compute='_compute_edi_log_count'
    )

    @api.depends('edi_log_ids')
    def _compute_edi_log_count(self):
        for picking in self:
            picking.edi_log_count = len(picking.edi_log_ids)

    def action_view_edi_logs(self):
        """View EDI generation logs for this delivery"""
        self.ensure_one()
        return {
            'name': 'EDI Logs',
            'type': 'ir.actions.act_window',
            'res_model': 'edi.log',
            'view_mode': 'list,form',
            'domain': [('picking_id', '=', self.id)],
            'context': {'default_picking_id': self.id},
        }

    def action_generate_edi(self):
        """Manually generate EDI for this delivery"""
        self.ensure_one()

        config = self.env['edi.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise UserError('No active EDI configuration found')

        generator = self.env['edi.generator']
        generator.generate_856_files(config, self)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'EDI 856 file generated successfully',
                'type': 'success',
                'sticky': False,
            }
        }