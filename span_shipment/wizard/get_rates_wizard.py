# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GetRatesWizard(models.TransientModel):
    _name = 'get.rates.wizard'
    _description = 'Get Shipping Rates'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Picking'
    )
    batch_id = fields.Many2one(
        'stock.picking.batch',
        string='Batch'
    )
    package_ids = fields.Many2many(
        'stock.quant.package',
        string='Packages'
    )

    # Carrier selection
    carrier_type = fields.Selection([
        ('ltl', 'LTL Freight'),
        ('parcel', 'Parcel')
    ], string='Carrier Type', default='ltl', required=True)

    delivery_carrier_id = fields.Many2one(
        'delivery.carrier',
        string='Delivery Method'
    )

    # Special services
    requires_liftgate = fields.Boolean(
        string='Liftgate Required'
    )
    requires_inside_delivery = fields.Boolean(
        string='Inside Delivery'
    )
    shipping_notes = fields.Text(
        string='Shipping Notes'
    )

    # Rate display
    show_rates = fields.Boolean(
        string='Show Rates',
        default=False
    )
    rate_line_ids = fields.One2many(
        'get.rates.wizard.line',
        'wizard_id',
        string='Available Rates'
    )

    # Shipment creation
    show_create_shipment = fields.Boolean(
        string='Show Create Shipment',
        default=False
    )
    selected_rate_id = fields.Many2one(
        'shipment.rate',
        string='Selected Rate'
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res['show_rates'] = False
        res['show_create_shipment'] = False
        # Set default carrier
        nexterus = self.env['delivery.carrier'].search([('delivery_type', '=', 'nexterus')], limit=1)
        if nexterus:
            res['delivery_carrier_id'] = nexterus.id
            res['carrier_type'] = 'ltl'
        return res

    @api.onchange('carrier_type')
    def _onchange_carrier_type(self):
        """Update carrier domain based on type"""
        if self.carrier_type == 'ltl':
            # Default to Nexterus
            nexterus = self.env['delivery.carrier'].search([
                ('delivery_type', '=', 'nexterus')
            ], limit=1)
            self.delivery_carrier_id = nexterus
        else:
            # Clear for parcel selection
            self.delivery_carrier_id = False

    @api.onchange('picking_id', 'batch_id')
    def _onchange_picking_batch(self):
        """Load special services from picking/batch"""
        if self.picking_id:
            self.requires_liftgate = self.picking_id.requires_liftgate
            self.requires_inside_delivery = self.picking_id.requires_inside_delivery
            self.shipping_notes = self.picking_id.shipping_notes
        elif self.batch_id:
            # Use first picking's settings
            if self.batch_id.picking_ids:
                first_picking = self.batch_id.picking_ids[0]
                self.requires_liftgate = first_picking.requires_liftgate
                self.requires_inside_delivery = first_picking.requires_inside_delivery
                self.shipping_notes = first_picking.shipping_notes

    def action_get_rates(self):
        """Get rates from selected carrier"""
        self.ensure_one()

        if not self.delivery_carrier_id:
            raise UserError(_('Please select a delivery method'))

        if not self.package_ids:
            raise UserError(_('No packages found'))

        # Save special services to picking/batch
        if self.picking_id:
            self.picking_id.write({
                'requires_liftgate': self.requires_liftgate,
                'requires_inside_delivery': self.requires_inside_delivery,
                'shipping_notes': self.shipping_notes,
            })
        elif self.batch_id:
            for picking in self.batch_id.picking_ids:
                picking.write({
                    'requires_liftgate': self.requires_liftgate,
                    'requires_inside_delivery': self.requires_inside_delivery,
                    'shipping_notes': self.shipping_notes,
                })

        if self.carrier_type == 'ltl':
            rates = self._get_ltl_rates()
        else:
            rates = self._get_parcel_rates()

        # Create rate lines for display
        self.rate_line_ids = [(5, 0, 0)]  # Clear existing
        for rate in rates:
            self.rate_line_ids = [(0, 0, rate)]

        self.show_rates = True

        # Return same wizard
        return {
            'name': _('Shipping Rates'),
            'type': 'ir.actions.act_window',
            'res_model': 'get.rates.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _get_ltl_rates(self):
        """Get LTL rates from Nexterus"""
        from ..models.nexterus_request import NexterusRequest

        # Get warehouse and partner
        if self.picking_id:
            warehouse = self.picking_id.picking_type_id.warehouse_id
            partner = self.picking_id.partner_id
        else:
            warehouse = self.batch_id.picking_ids[0].picking_type_id.warehouse_id
            partner = self.batch_id.picking_ids[0].partner_id

        # Prepare special services
        special_services = {
            'liftgate': self.requires_liftgate,
            'inside_delivery': self.requires_inside_delivery,
        }

        # Initialize Nexterus
        nexterus = NexterusRequest(self.delivery_carrier_id)

        # Get rates
        response = nexterus.get_rates(self.package_ids, partner, warehouse, special_services)

        # Store quote ID
        quote_id = response.get('quote_id')

        # Parse rates
        rates = []
        cheapest_price = None

        for idx, carrier_rate in enumerate(response.get('carrier_rates', [])):
            price = float(carrier_rate.get('ChargeAmount', 0))

            # Track cheapest
            is_cheapest = False
            if cheapest_price is None or price < cheapest_price:
                cheapest_price = price
                is_cheapest = True

            rates.append({
                'carrier_name': carrier_rate.get('CarrierName'),
                'carrier_scac': carrier_rate.get('CarrierScac'),
                'rate': price,
                'transit_days': carrier_rate.get('NumberOfDays', 'N/A'),
                'is_selected': is_cheapest,
                'nexterus_quote_id': quote_id,
            })

        return rates

    def _get_parcel_rates(self):
        """Get parcel rates from carriers using Odoo's native integration"""
        if not self.delivery_carrier_id:
            raise UserError(_('Please select a delivery carrier'))

        # Get destination partner and order reference
        if self.picking_id:
            partner = self.picking_id.partner_id
            # Try to get the sale order
            order = self.picking_id.sale_id if hasattr(self.picking_id,
                                                       'sale_id') and self.picking_id.sale_id else False
        else:
            partner = self.batch_id.picking_ids[0].partner_id
            # Try to get sale order from first picking
            first_picking = self.batch_id.picking_ids[0]
            order = first_picking.sale_id if hasattr(first_picking, 'sale_id') and first_picking.sale_id else False

        # Calculate total weight
        total_weight = sum(self.package_ids.mapped('shipping_weight'))

        try:
            # If we have a sale order, use it for rate calculation
            if order:
                # Use the carrier's rate_shipment method with the order
                vals = self.delivery_carrier_id.with_context(order_weight=total_weight).rate_shipment(order)
            else:
                # Create a mock order-like object for rate calculation
                order_vals = type('obj', (object,), {
                    'partner_id': partner,
                    'partner_shipping_id': partner,
                    'company_id': self.env.company,
                    'currency_id': self.env.company.currency_id,
                    'shipping_weight': total_weight,
                    'order_line': [],  # Empty order lines
                    'amount_total': 0,
                })()

                vals = self.delivery_carrier_id.rate_shipment(order_vals)

            if vals.get('success'):
                return [{
                    'carrier_name': self.delivery_carrier_id.name,
                    'carrier_scac': '',
                    'rate': vals.get('price', 0.0),
                    'transit_days': vals.get('warning_message', 'Standard'),
                    'is_selected': True,
                }]
            else:
                error_msg = vals.get('error_message', 'Failed to get rates')
                raise UserError(_('Error getting rates from %s: %s') % (self.delivery_carrier_id.name, error_msg))

        except Exception as e:
            # If the carrier doesn't support rate calculation, show a message
            if 'rate_shipment' in str(e):
                raise UserError(
                    _('%s does not support automatic rate calculation. Please use fixed price or rules-based pricing.') % self.delivery_carrier_id.name)
            else:
                raise UserError(_('Error getting rates from %s: %s') % (self.delivery_carrier_id.name, str(e)))

    def action_save_rates(self):
        """Save rates for later use"""
        self.ensure_one()

        # Get selected rate
        selected_line = self.rate_line_ids.filtered('is_selected')
        if not selected_line:
            raise UserError(_('Please select a rate'))

        # Create shipment rate record
        rate_vals = {
            'picking_id': self.picking_id.id if self.picking_id else False,
            'batch_id': self.batch_id.id if self.batch_id else False,
            'package_ids': [(6, 0, self.package_ids.ids)],
            'carrier_name': selected_line.carrier_name,
            'carrier_scac': selected_line.carrier_scac,
            'rate': selected_line.rate,
            'transit_days': selected_line.transit_days,
            'carrier_id': self.delivery_carrier_id.id,
            'nexterus_quote_id': selected_line.nexterus_quote_id,
            'state': 'active',
        }

        shipment_rate = self.env['shipment.rate'].create(rate_vals)

        # Success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Rate saved successfully'),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def action_create_shipment(self):
        """Create shipment with selected rate"""
        self.ensure_one()

        if self.selected_rate_id:
            # Creating from saved rate
            rate = self.selected_rate_id
        else:
            # Creating from current selection
            selected_line = self.rate_line_ids.filtered('is_selected')
            if not selected_line:
                raise UserError(_('Please select a rate'))
            if len(selected_line) > 1:
                raise UserError(_('Please select only one rate. You have selected %d rates.') % len(selected_line))

            # Create rate record first
            rate_vals = {
                'picking_id': self.picking_id.id if self.picking_id else False,
                'batch_id': self.batch_id.id if self.batch_id else False,
                'package_ids': [(6, 0, self.package_ids.ids)],
                'carrier_name': selected_line.carrier_name,
                'carrier_scac': selected_line.carrier_scac,
                'rate': selected_line.rate,
                'transit_days': selected_line.transit_days,
                'carrier_id': self.delivery_carrier_id.id,
                'nexterus_quote_id': selected_line.nexterus_quote_id,
                'state': 'active',
            }
            rate = self.env['shipment.rate'].create(rate_vals)

        # Check if already has carrier
        if self.picking_id and self.picking_id.carrier_id:
            raise UserError(_('This picking already has a carrier assigned'))
        if self.batch_id and self.batch_id.carrier_id:
            raise UserError(_('This batch already has a carrier assigned'))

        # Create shipment based on carrier type
        if self.carrier_type == 'ltl':
            self._create_ltl_shipment(rate)
        else:
            self._create_parcel_shipment(rate)

        # Mark rate as used
        rate.state = 'used'

        # Success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Shipment created successfully. PRO#: %s') % rate.pro_number,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _create_ltl_shipment(self, rate):
        """Create LTL shipment in Nexterus"""
        from ..models.nexterus_request import NexterusRequest

        # Get warehouse and partner
        if self.picking_id:
            warehouse = self.picking_id.picking_type_id.warehouse_id
            partner = self.picking_id.partner_id
        else:
            warehouse = self.batch_id.picking_ids[0].picking_type_id.warehouse_id
            partner = self.batch_id.picking_ids[0].partner_id

        # Check if carrier exists by SCAC, if not create it
        carrier = self.env['delivery.carrier'].search([
            ('nexterus_scac', '=', rate.carrier_scac)
        ], limit=1)

        if not carrier:
            # Create new carrier with the actual carrier name
            product = self.env.ref('span_shipment.product_product_span_shipment')
            carrier = self.env['delivery.carrier'].create({
                'name': rate.carrier_name,  # Use the actual carrier name from the rate
                'delivery_type': 'nexterus',
                'nexterus_scac': rate.carrier_scac,
                'product_id': product.id,
                'integration_level': 'rate_and_ship',
                'nexterus_username': self.delivery_carrier_id.nexterus_username,  # Copy credentials
                'nexterus_password': self.delivery_carrier_id.nexterus_password,
            })

        # Initialize Nexterus
        nexterus = NexterusRequest(self.delivery_carrier_id)

        # Special services
        special_services = {
            'liftgate': self.requires_liftgate,
            'inside_delivery': self.requires_inside_delivery,
        }

        # Create shipment
        response = nexterus.create_shipment(
            rate.nexterus_quote_id,
            rate.carrier_scac,
            self.package_ids,
            partner,
            warehouse,
            special_services
        )

        # Update rate with shipment info
        rate.write({
            'pro_number': response.get('pro_number'),
            'tracking_number': response.get('pro_number'),
            'shipment_date': fields.Datetime.now(),
            'carrier_id': carrier.id
        })

        # Update packages as shipped
        self.package_ids.write({'is_shipped': True})

        # Update picking/batch
        if self.picking_id:
            self.picking_id.write({
                'carrier_id': carrier.id,
                'carrier_tracking_ref': response.get('pro_number'),
            })
            # Propagate to related transfers
            self.picking_id._propagate_shipping_info()
        elif self.batch_id:
            self.batch_id.write({
                'carrier_id': carrier.id,
                'carrier_tracking_ref': response.get('pro_number'),
            })
            # Update all pickings
            for picking in self.batch_id.picking_ids:
                picking.write({
                    'carrier_id': carrier.id,
                    'carrier_tracking_ref': response.get('pro_number'),
                })
                picking._propagate_shipping_info()

    def _create_parcel_shipment(self, rate):
        """Create parcel shipment"""
        # This would integrate with FedEx/UPS/USPS modules
        # For now, create mock tracking
        tracking = 'TRACK' + fields.Datetime.now().strftime('%Y%m%d%H%M%S')

        rate.write({
            'tracking_number': tracking,
            'shipment_date': fields.Datetime.now(),
        })

        # Update packages
        self.package_ids.write({'is_shipped': True})

        # Update picking/batch
        if self.picking_id:
            self.picking_id.write({
                'carrier_id': self.delivery_carrier_id.id,
                'carrier_tracking_ref': tracking,
            })
        elif self.batch_id:
            self.batch_id.write({
                'carrier_id': self.delivery_carrier_id.id,
                'carrier_tracking_ref': tracking,
            })


class GetRatesWizardLine(models.TransientModel):
    _name = 'get.rates.wizard.line'
    _description = 'Rate Line'

    wizard_id = fields.Many2one(
        'get.rates.wizard',
        string='Wizard'
    )
    carrier_name = fields.Char(
        string='Carrier'
    )
    carrier_scac = fields.Char(
        string='SCAC'
    )
    rate = fields.Float(
        string='Rate'
    )
    currency_id = fields.Many2one(  # Added this field
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    transit_days = fields.Char(
        string='Transit Days'
    )
    is_selected = fields.Boolean(
        string='Select'
    )
    nexterus_quote_id = fields.Char(
        string='Quote ID'
    )

    @api.onchange('is_selected')
    def _onchange_is_selected(self):
        """Ensure only one rate is selected"""
        if self.is_selected:
            # Unselect others
            for line in self.wizard_id.rate_line_ids:
                if line != self:
                    line.is_selected = False