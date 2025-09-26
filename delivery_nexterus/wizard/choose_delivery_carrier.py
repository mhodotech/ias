# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.addons.delivery_nexterus.models.nexterus_request import NexterusRequest
import logging

_logger = logging.getLogger(__name__)


class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = 'choose.delivery.carrier'

    carrier_rates = fields.One2many(
        'carrier.rates',
        'wizard_id',
        string='Carrier Rates'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        compute='_compute_currency_id',
        store=True,
    )

    package_type_ids = fields.Many2many(
        'stock.package.type',
        string='Package Types',
        help='Select package types for shipment'
    )

    # Package details
    total_packages = fields.Integer(
        string='Total Packages',
        default=1,
        help='Total number of packages'
    )

    package_weight = fields.Float(
        string='Weight per Package (lbs)',
        help='Average weight per package'
    )

    package_length = fields.Float(
        string='Length (in)',
        default=48,
        help='Package length in inches'
    )

    package_width = fields.Float(
        string='Width (in)',
        default=40,
        help='Package width in inches'
    )

    package_height = fields.Float(
        string='Height (in)',
        default=48,
        help='Package height in inches'
    )

    use_for = fields.Selection(
        related='carrier_id.use_for',
        string='Use For'
    )

    comment = fields.Char('Comment')
    incoterms_id = fields.Many2one('account.incoterms', string='Incoterms')

    # Control fields
    show_rates = fields.Boolean(
        string='Show Rates',
        default=False,
        help='Show carrier rates section'
    )

    gateway_carrier_id = fields.Many2one(
        'delivery.carrier',
        string='Gateway Carrier',
        help='Nexterus gateway carrier for API calls'
    )

    @api.depends('order_id', 'order_id.pricelist_id')
    def _compute_currency_id(self):
        for record in self:
            if record.order_id and record.order_id.pricelist_id:
                record.currency_id = record.order_id.pricelist_id.currency_id
            else:
                record.currency_id = record.env.company.currency_id

    @api.onchange('carrier_id')
    def _onchange_carrier_id(self):
        """Set gateway carrier when Nexterus carrier is selected"""
        if self.carrier_id and self.carrier_id.delivery_type == 'nexterus':
            self.gateway_carrier_id = self.carrier_id.get_nexterus_gateway()

            # Set default package type
            if self.carrier_id.nexterus_default_package_type_id:
                self.package_type_ids = [(6, 0, [self.carrier_id.nexterus_default_package_type_id.id])]

    def get_prices(self):
        """Get freight rates from Nexterus"""
        if self.carrier_id.delivery_type != 'nexterus':
            return super().get_prices()

        _logger.info("Current quote ID before clearing: %s", self.order_id.nexterus_quote_id)

        # FORCE clear old quote - set to False explicitly
        self.order_id.write({'nexterus_quote_id': False})
        # self.order_id.flush(['nexterus_quote_id'])  # Force database write

        _logger.info("Quote ID after clearing: %s", self.order_id.nexterus_quote_id)

        # Validate inputs
        self._validate_inputs()

        # Prepare package data
        package_data = self._prepare_package_data()

        # Get rates from Nexterus
        order = self.order_id
        rates_response = self.carrier_id.nexterus_rate_shipment(package_data, order)

        if isinstance(rates_response, dict) and 'error' in rates_response:
            raise ValidationError(rates_response['error'])

        currency_id = order.pricelist_id.currency_id.id if order.pricelist_id else self.env.company.currency_id.id

        # Prepare rate display
        result = []
        cheapest_price = None
        cheapest_index = 0

        for idx, rate in enumerate(rates_response):
            # Check if carrier exists in Odoo
            existing_carrier = self.env['delivery.carrier'].search([
                ('nexterus_scac', '=', rate.get('carrier_scac')),
                ('delivery_type', '=', 'nexterus')
            ], limit=1)

            price = rate.get('price', 0)

            # Track cheapest
            if cheapest_price is None or price < cheapest_price:
                cheapest_price = price
                cheapest_index = idx

            result.append((0, 0, {
                'carrier_scac': rate.get('carrier_scac'),
                'name': rate.get('carrier_name'),
                'price': price,
                'service': f"{rate.get('days', 'N/A')} days",
                'service_id': rate.get('carrier_scac'),
                'estimated_delivery_date': rate.get('days', 'N/A'),
                'currency_id': currency_id,
                'carrier_id': existing_carrier.id if existing_carrier else False,
                'choose': idx == 0,  # Will update after to select cheapest
            }))

        # Update to select cheapest
        if result and cheapest_index < len(result):
            result[cheapest_index][2]['choose'] = True
            if cheapest_index != 0:
                result[0][2]['choose'] = False

        self.write({
            'carrier_rates': result,
            'show_rates': True,
        })

        # Return action to refresh the view
        return {
            'name': 'Carrier Rates',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'choose.delivery.carrier',
            'res_id': self.id,
            'target': 'new',
        }

    def _validate_inputs(self):
        """Validate wizard inputs"""
        if not self.carrier_id.nexterus_username or not self.carrier_id.nexterus_password:
            gateway = self.carrier_id.get_nexterus_gateway()
            if not gateway.nexterus_username or not gateway.nexterus_password:
                raise ValidationError(_('Nexterus credentials are required!'))

        if not self.package_type_ids:
            raise ValidationError(_('Please select at least one package type!'))

        if self.total_packages <= 0:
            raise ValidationError(_('Number of packages must be greater than zero!'))

        if self.package_weight <= 0:
            raise ValidationError(_('Package weight must be greater than zero!'))

    def _prepare_package_data(self):
        """Prepare package data for Nexterus API"""
        packages = []

        # Create package data based on selected package types
        for package_type in self.package_type_ids:
            packages.append({
                'package_type': package_type,
                'qty': self.total_packages,
                'weight': self.package_weight,
                'total_weight': self.package_weight * self.total_packages,
                'depth': self.package_length or package_type.packaging_length or 48,
                'width': self.package_width or package_type.width or 40,
                'height': self.package_height or package_type.height or 48,
            })

        return packages

    def button_confirm(self):
        """Confirm carrier selection and update order"""
        if self.carrier_id.delivery_type != 'nexterus':
            return super().button_confirm()

        # Get selected rate
        selected_rate = self.carrier_rates.filtered(lambda r: r.choose)
        if not selected_rate:
            raise ValidationError(_("Please select a carrier"))
        if len(selected_rate) > 1:
            raise ValidationError(_("You can only select one carrier"))

        # Check if carrier exists or create it
        carrier = self._get_or_create_carrier(selected_rate)

        # Apply margin and update price
        price = float(selected_rate.price)
        final_price = price * (1.0 + carrier.margin) + carrier.fixed_margin

        # Set delivery line on order with the actual carrier (not gateway)
        self.order_id.set_delivery_line(carrier, final_price)

        # Store Nexterus specific data
        self.order_id.write({
            'nexterus_carrier_price': price,
            'incoterm': self.incoterms_id.id if self.incoterms_id else False,
        })

        if self.order_id.state in ['sale', 'done']:
            pickings = self.order_id.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing' and p.state not in ['done', 'cancel']
            )
            pickings.write({'carrier_id': carrier.id})

        # Log in chatter
        self.order_id.message_post(
            body=_("Carrier selected: %s (SCAC: %s) - Price: %s %s") % (
                carrier.name,
                carrier.nexterus_scac,
                price,
                self.currency_id.symbol
            ),
            message_type='notification'
        )

    def _get_or_create_carrier(self, rate):
        """Get existing carrier or create new one from rate data"""
        # Check if carrier exists
        existing_carrier = self.env['delivery.carrier'].search([
            ('nexterus_scac', '=', rate.carrier_scac),
            ('delivery_type', '=', 'nexterus')
        ], limit=1)

        if existing_carrier:
            return existing_carrier

        # Create new carrier
        gateway = self.carrier_id.get_nexterus_gateway()
        new_carrier = self.env['delivery.carrier'].create_from_nexterus_rate({
            'carrier_scac': rate.carrier_scac,
            'carrier_name': rate.name,
        }, gateway)

        # Log creation
        _logger.info('Created new Nexterus carrier: %s (SCAC: %s)', new_carrier.name, new_carrier.nexterus_scac)

        return new_carrier

    def create_nexterus_shipment(self):
        """Create shipment in Nexterus with selected carrier"""
        selected_rate = self.carrier_rates.filtered(lambda r: r.choose)
        if not selected_rate:
            raise ValidationError(_("Please select a carrier"))

        if len(selected_rate) > 1:
            raise ValidationError(_("You can only select one carrier"))

        # First confirm the selection (this will create carrier if needed)
        self.button_confirm()

        # Check if we have a quote ID
        if not self.order_id.nexterus_quote_id:
            raise ValidationError(_("No quote ID found. Please get rates first."))

        # Get the actual carrier (may have been created)
        carrier = self._get_or_create_carrier(selected_rate)

        # Create the shipment in Nexterus using the carrier's SCAC
        try:
            gateway = carrier.get_nexterus_gateway()
            nexterus = NexterusRequest(gateway)

            response = nexterus.create_shipment(
                self.order_id,
                carrier.nexterus_scac,
                self.order_id.nexterus_quote_id
            )

            if response.get('errors'):
                error_msg = '\n'.join(response['errors'])
                raise ValidationError(f"Nexterus Error: {error_msg}")

            # Update order with shipment info
            if response.get('pro_number'):
                # Update sale order
                update_vals = {
                    'nexterus_pro_number': response['pro_number'],
                    'nexterus_bol_url': response.get('links', {}).get('documents', {}).get('BillLading', ''),
                    'nexterus_label_url': response.get('links', {}).get('documents', {}).get('Label', ''),
                    'nexterus_tracking_url': response.get('links', {}).get('documents', {}).get('ShipmentTracking', ''),
                }
                self.order_id.write(update_vals)

                # If sale order is confirmed, update delivery orders
                if self.order_id.state in ['sale', 'done']:
                    pickings = self.order_id.picking_ids
                    for picking in pickings:
                        picking.write({
                            'carrier_id': carrier.id,
                            'carrier_tracking_ref': response['pro_number'],
                            'nexterus_pro_number': response['pro_number'],
                            'nexterus_bol_url': update_vals['nexterus_bol_url'],
                            'nexterus_label_url': update_vals['nexterus_label_url'],
                            'nexterus_tracking_url': update_vals['nexterus_tracking_url'],
                        })
                        picking.message_post(
                            body=_("Nexterus shipment updated from Sales Order. PRO#: %s") % response['pro_number'],
                            message_type='notification'
                        )

                # Close wizard with success message
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Shipment created successfully. PRO#: %s') % response['pro_number'],
                        'type': 'success',
                        'sticky': False,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            else:
                raise ValidationError(_("Shipment created but no PRO number received"))

        except Exception as e:
            raise ValidationError(str(e))