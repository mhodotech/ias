# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Nexterus specific fields
    nexterus_pro_number = fields.Char(
        string='PRO #',
        copy=False,
        readonly=True,
        tracking=True  # Enable tracking for chatter
    )

    # Accessorial services
    nexterus_inside_delivery = fields.Boolean(
        string='Inside Delivery',
        help='Requires inside delivery service',
        tracking=True
    )

    nexterus_liftgate_service = fields.Boolean(
        string='Liftgate Service',
        help='Requires liftgate at delivery',
        tracking=True
    )

    # Document URLs (kept but not shown in UI)
    nexterus_bol_url = fields.Char(
        string='Bill of Lading URL',
        copy=False,
        readonly=True
    )

    nexterus_label_url = fields.Char(
        string='Label URL',
        copy=False,
        readonly=True
    )

    nexterus_tracking_url = fields.Char(
        string='Tracking URL',
        copy=False,
        readonly=True
    )

    def action_view_bol(self):
        """Open Bill of Lading document"""
        self.ensure_one()
        if not self.nexterus_bol_url:
            raise UserError(_('Bill of Lading not available yet.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.nexterus_bol_url,
            'target': 'new',
        }

    def action_view_label(self):
        """Open shipping label"""
        self.ensure_one()
        if not self.nexterus_label_url:
            raise UserError(_('Shipping label not available yet.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.nexterus_label_url,
            'target': 'new',
        }

    def action_track_shipment(self):
        """Open tracking page"""
        self.ensure_one()
        if not self.nexterus_tracking_url:
            raise UserError(_('Tracking information not available yet.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.nexterus_tracking_url,
            'target': 'new',
        }

    def open_website_url(self):
        """Override to use Nexterus tracking URL"""
        self.ensure_one()
        if self.carrier_id.delivery_type == 'nexterus' and self.nexterus_tracking_url:
            return {
                'type': 'ir.actions.act_url',
                'name': "Shipment Tracking Page",
                'target': 'new',
                'url': self.nexterus_tracking_url,
            }
        return super().open_website_url()

    @api.model_create_multi
    def create(self, vals_list):
        """Copy Nexterus info from sale order when creating picking"""
        for vals in vals_list:
            if 'origin' in vals and vals.get('origin'):
                sale_order = self.env['sale.order'].search([
                    ('name', '=', vals['origin'])
                ], limit=1)

                if sale_order:
                    # Copy all Nexterus data if available
                    if sale_order.nexterus_pro_number:
                        vals['carrier_tracking_ref'] = sale_order.nexterus_pro_number
                        vals['nexterus_pro_number'] = sale_order.nexterus_pro_number
                    if sale_order.nexterus_bol_url:
                        vals['nexterus_bol_url'] = sale_order.nexterus_bol_url
                    if sale_order.nexterus_label_url:
                        vals['nexterus_label_url'] = sale_order.nexterus_label_url
                    if sale_order.nexterus_tracking_url:
                        vals['nexterus_tracking_url'] = sale_order.nexterus_tracking_url
                    if sale_order.carrier_id:
                        vals['carrier_id'] = sale_order.carrier_id.id

        return super().create(vals_list)

    def button_validate(self):
        """Override to create Nexterus shipment when validating"""
        # First do standard validation
        res = super().button_validate()

        # Check if this is a Nexterus carrier delivery
        for picking in self.filtered(lambda p: p.carrier_id and p.carrier_id.delivery_type == 'nexterus'):
            if not picking.nexterus_pro_number and picking.picking_type_code == 'outgoing':
                # Try to create shipment automatically
                try:
                    picking.carrier_id.nexterus_send_shipping([picking])
                except Exception as e:
                    # Log but don't block validation
                    picking.message_post(
                        body=_("Failed to create Nexterus shipment: %s") % str(e),
                        message_type='notification'
                    )

        return res