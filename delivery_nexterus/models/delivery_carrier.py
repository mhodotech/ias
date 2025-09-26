# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from .nexterus_request import NexterusRequest

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('nexterus', 'Nexterus')],
        ondelete={'nexterus': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})}
    )

    # Nexterus SCAC code for carrier identification
    nexterus_scac = fields.Char(
        string="SCAC Code",
        help="Standard Carrier Alpha Code for Nexterus integration"
    )

    # Nexterus credentials - only for main Nexterus gateway carrier
    nexterus_username = fields.Char(
        string="Nexterus Username",
        help="Your Nexterus API username (only needed for gateway carrier)"
    )
    nexterus_password = fields.Char(
        string="Nexterus Password",
        help="Your Nexterus API password (only needed for gateway carrier)"
    )

    # Nexterus ID for matching
    nexterus_carrier_id = fields.Char(
        string="Nexterus ID",
        help="Carrier ID in Nexterus system for matching"
    )

    # Gateway carrier reference - for child carriers created from Nexterus
    nexterus_gateway_id = fields.Many2one(
        'delivery.carrier',
        string="Nexterus Gateway",
        help="Parent Nexterus gateway carrier used for API calls"
    )

    # Nexterus configuration
    nexterus_default_freight_class = fields.Selection([
        ('50', 'Class 50'),
        ('55', 'Class 55'),
        ('60', 'Class 60'),
        ('65', 'Class 65'),
        ('70', 'Class 70'),
        ('77', 'Class 77.5'),
        ('85', 'Class 85'),
        ('92', 'Class 92.5'),
        ('100', 'Class 100'),
        ('110', 'Class 110'),
        ('125', 'Class 125'),
        ('150', 'Class 150'),
        ('175', 'Class 175'),
        ('200', 'Class 200'),
        ('250', 'Class 250'),
        ('300', 'Class 300'),
        ('400', 'Class 400'),
        ('500', 'Class 500'),
    ],
        string="Default Freight Class",
        default='85',
        help="Default freight classification to use when not specified on product"
    )

    nexterus_default_package_type_id = fields.Many2one(
        "stock.package.type",
        string="Default Package Type",
        help="Default package type for Nexterus shipments"
    )

    # Accessorial options
    nexterus_liftgate_origin = fields.Boolean(
        string="Liftgate at Origin",
        help="Default to requiring liftgate at pickup"
    )
    nexterus_liftgate_destination = fields.Boolean(
        string="Liftgate at Destination",
        help="Default to requiring liftgate at delivery"
    )
    nexterus_inside_delivery = fields.Boolean(
        string="Inside Delivery",
        help="Default to inside delivery service"
    )
    nexterus_notification_required = fields.Boolean(
        string="Delivery Notification",
        help="Default to requiring delivery notification"
    )
    nexterus_appointment_required = fields.Boolean(
        string="Appointment Required",
        help="Default to requiring delivery appointment"
    )
    nexterus_call_for_pickup = fields.Boolean(
        string="Call Carrier for Pickup",
        help="Have Nexterus call carrier to schedule pickup"
    )

    use_for = fields.Selection([
        ('sale', 'Sale'),
        ('purchase', 'Purchase'),
        ('picking', 'Picking')
    ], default="sale", string='Use For')

    @api.constrains('nexterus_username', 'nexterus_password')
    def _check_nexterus_credentials(self):
        # Skip while modules are being installed/upgraded or tests/imports
        if (self.env.context.get('install_mode')
                or self.env.context.get('module')
                or self.env.context.get('testing')
                or self.env.context.get('import_file')):
            return

        for rec in self:
            # Only check credentials for gateway carriers (those without gateway_id)
            if rec.delivery_type == 'nexterus' and rec.active and not rec.nexterus_gateway_id:
                if not rec.nexterus_username or not rec.nexterus_password:
                    raise ValidationError(_("Nexterus username and password are required for gateway carriers."))

    def get_nexterus_gateway(self):
        """Get the Nexterus gateway carrier for API calls"""
        self.ensure_one()
        if self.nexterus_gateway_id:
            return self.nexterus_gateway_id
        return self

    def nexterus_rate_shipment(self, package_types, order):
        """Get shipping rates from Nexterus"""
        self.ensure_one()
        if self.delivery_type != 'nexterus':
            return []

        try:
            # Use gateway carrier for API call
            gateway = self.get_nexterus_gateway()
            nexterus = NexterusRequest(gateway)
            response = nexterus.get_rates(order, package_types)

            if response.get('errors'):
                return {'error': response['errors']}

            rates = []
            for carrier_rate in response.get('carrier_rates', []):
                rate_data = {
                    'carrier_scac': carrier_rate.get('CarrierScac'),
                    'carrier_name': carrier_rate.get('CarrierName'),
                    'price': float(carrier_rate.get('ChargeAmount', 0)),
                    'days': carrier_rate.get('NumberOfDays', 'N/A'),
                    'quote_url': carrier_rate.get('QuoteUrl'),
                }
                rates.append(rate_data)

            # Store quote ID for later use
            if response.get('quote_id'):
                order.nexterus_quote_id = response['quote_id']

            return rates

        except Exception as e:
            _logger.error(f"Nexterus rate error: {str(e)}")
            return {'error': str(e)}

    def nexterus_send_shipping(self, pickings):
        """Create shipments in Nexterus"""
        self.ensure_one()

        # Use gateway carrier for API call
        gateway = self.get_nexterus_gateway()
        nexterus = NexterusRequest(gateway)
        res = []

        for picking in pickings:
            sale_order = picking.sale_id
            if not sale_order:
                sale_order = self.env['sale.order'].search([
                    ('name', '=', picking.origin)
                ], limit=1)

            if not sale_order:
                raise UserError(_('Cannot find sales order for picking %s') % picking.name)

            if not sale_order.nexterus_quote_id:
                raise UserError(_('No Nexterus quote found. Please get rates first.'))

            # Use SCAC from this carrier (not from selected_carrier field)
            if not self.nexterus_scac:
                raise UserError(_('No SCAC code configured for carrier %s') % self.name)

            # Create shipment with this carrier's SCAC
            response = nexterus.create_shipment(
                sale_order,
                self.nexterus_scac,  # Use this carrier's SCAC
                sale_order.nexterus_quote_id
            )

            if response.get('errors'):
                error_msg = '\n'.join(response['errors'])
                raise ValidationError(f"Nexterus Error: {error_msg}")

            # Update records with shipment info
            shipment_data = {
                'carrier_tracking_ref': response.get('pro_number'),
                'nexterus_pro_number': response.get('pro_number'),
            }

            # Get document links
            if response.get('links', {}).get('documents'):
                docs = response['links']['documents']
                if docs.get('BillLading'):
                    shipment_data['nexterus_bol_url'] = docs['BillLading']
                if docs.get('Label'):
                    shipment_data['nexterus_label_url'] = docs['Label']
                if docs.get('ShipmentTracking'):
                    shipment_data['nexterus_tracking_url'] = docs['ShipmentTracking']

            picking.write(shipment_data)

            # Log in chatter
            picking.message_post(
                body=_("Nexterus shipment created. PRO#: %s") % response.get('pro_number'),
                message_type='notification'
            )

            res.append({
                'tracking_number': response.get('pro_number'),
                'exact_price': float(self.margin) * float(sale_order.nexterus_carrier_price or 0.0) + float(
                    self.fixed_margin)
            })

        return res

    def action_test_nexterus_connection(self):
        """Test Nexterus API connection"""
        self.ensure_one()

        if self.delivery_type != 'nexterus':
            raise ValidationError(_('This is not a Nexterus carrier'))

        # Use gateway for testing
        gateway = self.get_nexterus_gateway()
        if not gateway.nexterus_username or not gateway.nexterus_password:
            raise ValidationError(_('Please enter Nexterus credentials first'))

        try:
            nexterus = NexterusRequest(gateway)

            # Create a minimal test request with dummy data
            test_data = {
                'header': {
                    'RequestType': 'Add',
                    'ServiceType': 'LTL',
                    'ShipmentMethod': 'LTL',
                    'GenerateRates': 'Y',
                    'PersonCalling': 'TEST',
                    'Prepaid': 'Y',
                    'FreightDirection': 'OUTBOUND',
                    'ShipDate': (fields.Date.today() + timedelta(days=1)).strftime('%m/%d/%Y'),
                },
                'address': {
                    'shipper': {
                        'Name': 'Test Shipper',
                        'Street': '123 Test St',
                        'City': 'Greenville',
                        'StateCode': 'SC',
                        'PostalCode': '29615',
                        'ContactPhone': '864-000-0000'
                    },
                    'consignee': {
                        'Name': 'Test Consignee',
                        'Street': '456 Test Ave',
                        'City': 'Los Angeles',
                        'StateCode': 'CA',
                        'PostalCode': '90001',
                        'ContactPhone': '213-000-0000'
                    }
                },
                'commodities': [{
                    'CommodityName': 'TEST',
                    'NumberOfSkids': '1',
                    'Weight': '100',
                    'ClassNumber': '85'
                }]
            }

            xml_request = nexterus._build_xml_request(test_data)
            response = nexterus._make_api_request(xml_request)

            # If we get a quote ID back, connection is successful
            if response.get('quote_id'):
                message = _('Connection successful! Test quote ID: %s') % response['quote_id']
                msg_type = 'success'
            elif response.get('carrier_rates'):
                message = _('Connection successful! Received %d carrier rates') % len(response['carrier_rates'])
                msg_type = 'success'
            elif response.get('errors'):
                # Some errors are expected for test data, but connection works
                if any('authentication' in str(e).lower() for e in response['errors']):
                    raise ValidationError(_('Authentication failed. Please check credentials.'))
                message = _('Connection works but test data validation failed (expected)')
                msg_type = 'warning'
            else:
                message = _('Connection established but unexpected response received')
                msg_type = 'warning'

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Nexterus Connection Test'),
                    'message': message,
                    'type': msg_type,
                }
            }

        except Exception as e:
            _logger.error(f"Nexterus connection test failed: {str(e)}")
            raise ValidationError(_('Connection failed: %s') % str(e))

    @api.model
    def create_from_nexterus_rate(self, rate_data, gateway_carrier):
        """Create a new carrier from Nexterus rate data"""
        # Check if carrier already exists
        existing = self.search([
            ('nexterus_scac', '=', rate_data['carrier_scac']),
            ('delivery_type', '=', 'nexterus')
        ], limit=1)

        if existing:
            return existing

        # Use the base Nexterus product instead of creating a new one
        base_product = self.env.ref('delivery_nexterus.product_product_delivery_nexterus', raise_if_not_found=False)
        if not base_product:
            # Fallback: create product if base doesn't exist
            base_product = self.env['product.product'].create({
                'name': f"{rate_data['carrier_name']} - Nexterus",
                'default_code': f"NXT_{rate_data['carrier_scac']}",
                'type': 'service',
                'categ_id': self.env.ref('delivery.product_category_deliveries').id,
                'sale_ok': False,
                'purchase_ok': False,
                'list_price': 0.0,
                'invoice_policy': 'order',
            })

        product = base_product

        # Create carrier
        return self.create({
            'name': rate_data['carrier_name'],
            'delivery_type': 'nexterus',
            'nexterus_scac': rate_data['carrier_scac'],
            'nexterus_gateway_id': gateway_carrier.id,
            'product_id': product.id,
            'integration_level': 'rate_and_ship',
            'use_for': 'sale',
            # Copy settings from gateway
            'nexterus_default_freight_class': gateway_carrier.nexterus_default_freight_class,
            'nexterus_default_package_type_id': gateway_carrier.nexterus_default_package_type_id.id if gateway_carrier.nexterus_default_package_type_id else False,
            'nexterus_liftgate_origin': gateway_carrier.nexterus_liftgate_origin,
            'nexterus_liftgate_destination': gateway_carrier.nexterus_liftgate_destination,
            'nexterus_inside_delivery': gateway_carrier.nexterus_inside_delivery,
            'nexterus_notification_required': gateway_carrier.nexterus_notification_required,
            'nexterus_appointment_required': gateway_carrier.nexterus_appointment_required,
            'nexterus_call_for_pickup': gateway_carrier.nexterus_call_for_pickup,
        })