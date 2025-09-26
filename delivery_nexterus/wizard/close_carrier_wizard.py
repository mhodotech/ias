# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CloseCarrierWizard(models.TransientModel):
    _name = 'close.carrier.wizard'
    _description = 'Close Carrier Wizard'

    picking_ids = fields.Many2many(
        'stock.picking',
        string='Deliveries to Close',
        required=True
    )

    email_ids = fields.Many2many(
        'carrier.close.config',
        string='Emails to Notify',
        compute='_compute_email_ids'
    )

    carrier_names = fields.Text(
        string='Carriers',
        compute='_compute_carrier_names',
        readonly=True
    )

    delivery_order_names = fields.Text(
        string='Delivery Orders',
        compute='_compute_delivery_order_names',
        readonly=True
    )

    @api.depends()
    def _compute_email_ids(self):
        """Get all active email configurations"""
        for record in self:
            configs = self.env['carrier.close.config'].search([('active', '=', True)])
            record.email_ids = configs

    @api.depends('picking_ids')
    def _compute_carrier_names(self):
        """Get unique carrier names from selected pickings"""
        for record in self:
            carriers = record.picking_ids.mapped('carrier_id.name')
            # Remove duplicates while preserving order
            unique_carriers = list(dict.fromkeys(carriers))
            record.carrier_names = ', '.join(unique_carriers) if unique_carriers else 'N/A'

    @api.depends('picking_ids')
    def _compute_delivery_order_names(self):
        """Get delivery order names"""
        for record in self:
            names = record.picking_ids.mapped('name')
            record.delivery_order_names = ', '.join(names) if names else 'N/A'

    def action_close_carriers(self):
        """Close selected deliveries and send notifications"""
        if not self.picking_ids:
            raise UserError(_('No deliveries selected to close.'))

        # Validate that all pickings are ready
        not_ready = self.picking_ids.filtered(lambda p: p.state != 'assigned')
        if not_ready:
            raise UserError(_(
                'The following deliveries are not ready to close: %s\n'
                'Only deliveries in "Ready" state can be closed.'
            ) % ', '.join(not_ready.mapped('name')))

        # Update picking status to done
        for picking in self.picking_ids:
            # Validate the picking
            picking.button_validate()

            # Log in chatter
            picking.message_post(
                body=_("Carrier closed by %s through Close Carrier action") % self.env.user.name,
                message_type='notification'
            )

        # Send email notifications
        if self.email_ids:
            self._send_notifications()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d deliveries have been closed and notifications sent.') % len(self.picking_ids),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _send_notifications(self):
        """Send email notifications to configured recipients"""
        template = self.env.ref('delivery_nexterus.email_template_carrier_closed', raise_if_not_found=False)

        if not template:
            _logger.warning('Email template for carrier closed not found')
            return

        # Send individual emails to each configured recipient
        for email_config in self.email_ids:
            if email_config.email:
                try:
                    template.send_mail(
                        self.id,
                        force_send=True,
                        email_values={'email_to': email_config.email}
                    )
                    _logger.info('Carrier closed notification sent to %s', email_config.email)
                except Exception as e:
                    _logger.error('Failed to send email to %s: %s', email_config.email, str(e))

    @api.model
    def action_open_wizard(self):
        """Open the wizard with pre-selected pickings"""
        return {
            'name': _('Close Carriers'),
            'type': 'ir.actions.act_window',
            'res_model': 'close.carrier.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }