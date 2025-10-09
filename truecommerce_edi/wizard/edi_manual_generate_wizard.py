from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class EDIManualGenerateWizard(models.TransientModel):
    _name = 'edi.manual.generate.wizard'
    _description = 'Manual EDI Generation Wizard'

    date_from = fields.Date(
        'From Date',
        required=True,
        default=lambda self: datetime.now() - timedelta(days=1)
    )
    date_to = fields.Date(
        'To Date',
        required=True,
        default=lambda self: datetime.now()
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Customers',
        domain=[('edi_enabled', '=', True)],
        help='Leave empty to generate for all EDI enabled customers'
    )
    picking_ids = fields.Many2many(
        'stock.picking',
        string='Specific Deliveries',
        domain=[
            ('picking_type_id.code', '=', 'outgoing'),
            ('state', '=', 'done')
        ],
        help='Select specific deliveries to generate EDI for'
    )
    regenerate = fields.Boolean(
        'Regenerate Existing',
        default=False,
        help='Regenerate EDI files even if already generated'
    )

    def action_generate(self):
        """Generate EDI files based on wizard parameters"""
        self.ensure_one()

        config = self.env['edi.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise UserError('No active EDI configuration found')

        # Build domain for pickings
        domain = [
            ('picking_type_id.code', '=', 'outgoing'),
            ('state', '=', 'done'),
        ]

        if self.picking_ids:
            # Use specific pickings
            pickings = self.picking_ids
        else:
            # Use date range
            if self.date_from:
                domain.append(('date_done', '>=', self.date_from))
            if self.date_to:
                domain.append(('date_done', '<=', self.date_to))

            if self.partner_ids:
                domain.append(('partner_id', 'in', self.partner_ids.ids))
            else:
                # Only EDI enabled partners
                domain.append(('partner_id.edi_enabled', '=', True))

            if not self.regenerate:
                domain.append(('edi_file_generated', '=', False))

            pickings = self.env['stock.picking'].search(domain)

        if not pickings:
            raise UserError('No deliveries found matching the criteria')

        # Generate EDI files
        generator = self.env['edi.generator']
        generator.generate_856_files(config, pickings)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Generated EDI files for {len(pickings)} deliveries',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }