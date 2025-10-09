# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ShipmentRate(models.Model):
    _name = 'shipment.rate'
    _description = 'Shipment Rate'
    _order = 'create_date desc'
    _rec_name = 'carrier_name'

    # Relations
    picking_id = fields.Many2one(
        'stock.picking',
        string='Picking',
        ondelete='cascade'
    )
    batch_id = fields.Many2one(
        'stock.picking.batch',
        string='Batch',
        ondelete='cascade'
    )
    package_ids = fields.Many2many(
        'stock.quant.package',
        string='Packages'
    )

    # Carrier information
    carrier_name = fields.Char(
        string='Carrier',
        required=True
    )
    carrier_scac = fields.Char(
        string='SCAC Code'
    )
    carrier_id = fields.Many2one(
        'delivery.carrier',
        string='Delivery Method'
    )

    # Rate information
    rate = fields.Float(
        string='Rate',
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    transit_days = fields.Char(
        string='Transit Days'
    )

    # State management
    state = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('used', 'Used'),
    ], string='State', default='active', required=True)

    expiration_date = fields.Datetime(
        string='Expiration Date',
        required=True
    )

    # Shipment information (filled when used)
    pro_number = fields.Char(
        string='PRO Number'
    )
    tracking_number = fields.Char(
        string='Tracking Number'
    )
    shipment_date = fields.Datetime(
        string='Shipment Date'
    )

    # Nexterus specific
    nexterus_quote_id = fields.Char(
        string='Nexterus Quote ID'
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Set expiration date on creation"""
        for vals in vals_list:
            if 'expiration_date' not in vals:
                carrier_id = vals.get('carrier_id')
                if carrier_id:
                    carrier = self.env['delivery.carrier'].browse(carrier_id)
                    if carrier.delivery_type == 'nexterus':
                        hours = carrier.nexterus_rate_expiration or 24
                        vals['expiration_date'] = datetime.now() + timedelta(hours=hours)
                    else:
                        vals['expiration_date'] = datetime.now() + timedelta(hours=24)
                else:
                    vals['expiration_date'] = datetime.now() + timedelta(hours=24)
        return super().create(vals_list)

    def action_create_shipment(self):
        """Create shipment from this rate"""
        self.ensure_one()

        # Check if expired
        if self.state == 'expired' or self.expiration_date < fields.Datetime.now():
            raise UserError(_('This rate has expired. Please get fresh rates.'))

        if self.state == 'used':
            raise UserError(_('This rate has already been used to create a shipment.'))

        requires_liftgate = False
        requires_inside_delivery = False

        if self.picking_id:
            requires_liftgate = self.picking_id.requires_liftgate
            requires_inside_delivery = self.picking_id.requires_inside_delivery
        elif self.batch_id and self.batch_id.picking_ids:
            first_picking = self.batch_id.picking_ids[0]
            requires_liftgate = first_picking.requires_liftgate
            requires_inside_delivery = first_picking.requires_inside_delivery

            # Open wizard to create shipment with all necessary data
        wizard = self.env['get.rates.wizard'].create({
            'picking_id': self.picking_id.id if self.picking_id else False,
            'batch_id': self.batch_id.id if self.batch_id else False,
            'package_ids': [(6, 0, self.package_ids.ids)],  # Pass the packages
            'selected_rate_id': self.id,
            'show_rates': False,
            'show_create_shipment': True,
            'delivery_carrier_id': self.carrier_id.id,
            'carrier_type': 'ltl' if self.carrier_id.delivery_type == 'nexterus' else 'parcel',
            'requires_liftgate': requires_liftgate,
            'requires_inside_delivery': requires_inside_delivery,
        })

        return {
            'name': _('Create Shipment'),
            'type': 'ir.actions.act_window',
            'res_model': 'get.rates.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'next': {'type': 'ir.actions.act_window_close'},
        }

    def action_refresh_rates(self):
        """Get fresh rates for same packages"""
        self.ensure_one()

        # Create wizard with same packages
        wizard = self.env['get.rates.wizard'].create({
            'picking_id': self.picking_id.id if self.picking_id else False,
            'batch_id': self.batch_id.id if self.batch_id else False,
            'package_ids': [(6, 0, self.package_ids.ids)],
        })

        return {
            'name': _('Get Fresh Rates'),
            'type': 'ir.actions.act_window',
            'res_model': 'get.rates.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def check_expired_rates(self):
        """Check and update expired rates"""
        expired_rates = self.search([
            ('state', '=', 'active'),
            ('expiration_date', '<', fields.Datetime.now())
        ])
        expired_rates.write({'state': 'expired'})
        return True