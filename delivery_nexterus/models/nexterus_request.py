# -*- coding: utf-8 -*-
import logging
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from urllib.parse import urlencode

from odoo import fields, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

NEXTERUS_NAMESPACE = "http://www.nexterus.com/RequestShipment/LTL/v3"


class NexterusRequest:
    """Handle communication with Nexterus API"""

    def __init__(self, carrier):
        """Initialize Nexterus API handler"""
        self.carrier = carrier
        if carrier.prod_environment:
            self.url = 'https://fusioncenter.nexterus.com/FusionCenter/ws'
            _logger.info("🔴 Using Nexterus PRODUCTION environment")
        else:
            self.url = 'https://test.nexterus.com/FusionCenter/ws'
            _logger.info("🟢 Using Nexterus TEST environment")

        _logger.info("Nexterus URL: %s", self.url)
        _logger.info("Nexterus Username: %s", carrier.nexterus_username)

        self.session = requests.Session()
        self.session.auth = (carrier.nexterus_username, carrier.nexterus_password)

    def _build_xml_request(self, shipment_data):
        """Build XML request for Nexterus API"""
        # Create root element with namespace - ensure quotes are included
        root = ET.Element("TBB")
        root.set("xmlns", "http://www.nexterus.com/RequestShipment/LTL/v3")

        shipment = ET.SubElement(root, "Shipment")

        # Build Header - maintain order as in API docs
        header = ET.SubElement(shipment, "Header")
        header_order = ['RequestType', 'ServiceType', 'ShipmentMethod', 'SourceReferenceNumber',
                        'SelectedCarrier', 'ScheduleShipment', 'GenerateRates', 'AutoSelectCarrier',
                        'GeneratePRONumber', 'CallCarrierForPickup', 'PersonCalling', 'Prepaid',
                        'FreightDirection', 'ShipDate', 'TimeShipperCloses', 'TimeFreightReady']

        for key in header_order:
            if key in shipment_data.get('header', {}):
                value = shipment_data['header'][key]
                if value is not None:
                    ET.SubElement(header, key).text = str(value)

        # Build Accessorials if present
        if shipment_data.get('accessorials'):
            accessorials = ET.SubElement(shipment, "Accessorials")
            for key, value in shipment_data['accessorials'].items():
                if value is not None:
                    ET.SubElement(accessorials, key).text = str(value)

        # Build Address
        if shipment_data.get('address'):
            address = ET.SubElement(shipment, "Address")

            # Shipper
            if shipment_data['address'].get('shipper'):
                shipper = ET.SubElement(address, "Shipper")
                for key, value in shipment_data['address']['shipper'].items():
                    if value is not None and value != '':
                        ET.SubElement(shipper, key).text = str(value)

            # Consignee
            if shipment_data['address'].get('consignee'):
                consignee = ET.SubElement(address, "Consignee")
                for key, value in shipment_data['address']['consignee'].items():
                    if value is not None and value != '':
                        ET.SubElement(consignee, key).text = str(value)

        # Build Commodities - maintain order as in API docs
        if shipment_data.get('commodities'):
            commodities = ET.SubElement(shipment, "Commodities")
            commodity_order = ['CommodityName', 'NumberOfSkids', 'NumberOfPieces', 'PieceType',
                               'UnitOfWeight', 'Weight', 'ClassNumber', 'UnitOfMeasure',
                               'Length', 'Width', 'Height']

            for commodity_data in shipment_data['commodities']:
                commodity = ET.SubElement(commodities, "Commodity")
                for key in commodity_order:
                    if key in commodity_data and commodity_data[key] is not None:
                        ET.SubElement(commodity, key).text = str(commodity_data[key])

        # Convert to string with proper declaration
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_str += ET.tostring(root, encoding='unicode')
        return xml_str


    def _parse_xml_response(self, xml_string):
        """Parse XML response from Nexterus API"""
        try:
            root = ET.fromstring(xml_string)

            # Remove namespace for easier parsing
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]

            response_data = {}

            # Parse Response section
            response = root.find('.//Response')
            if response is not None:
                # Get TBBRateQuoteID
                quote_id = response.find('TBBRateQuoteID')
                if quote_id is not None:
                    response_data['quote_id'] = quote_id.text

                # Parse carrier rates
                carrier_rates = []
                for carrier_quote in response.findall('.//CarrierQuote'):
                    rate_data = {}
                    for child in carrier_quote:
                        rate_data[child.tag] = child.text
                    carrier_rates.append(rate_data)
                response_data['carrier_rates'] = carrier_rates

                # Parse selected carrier if present
                selected_carrier = response.find('SelectedCarrier')
                if selected_carrier is not None:
                    selected_data = {}
                    for child in selected_carrier:
                        if child.tag in ['CarrierOriginTerminal', 'CarrierDestinationTerminal']:
                            terminal_data = {}
                            for terminal_child in child:
                                terminal_data[terminal_child.tag] = terminal_child.text
                            selected_data[child.tag] = terminal_data
                        else:
                            selected_data[child.tag] = child.text
                    response_data['selected_carrier'] = selected_data

                # Parse PRO number if present
                pro_number = response.find('PRONumber')
                if pro_number is not None:
                    response_data['pro_number'] = pro_number.text

                # Parse links
                links = response.find('Links')
                if links is not None:
                    links_data = {}
                    documents = links.find('Documents')
                    if documents is not None:
                        doc_data = {}
                        for doc in documents:
                            doc_data[doc.tag] = doc.text
                        links_data['documents'] = doc_data
                    response_data['links'] = links_data

            # Parse errors if present
            errors = root.findall('.//Error')
            if errors:
                response_data['errors'] = [error.text for error in errors]

            return response_data

        except ET.ParseError as e:
            _logger.error(f"XML Parse Error: {e}")
            return {'errors': [f"Failed to parse response: {str(e)}"]}

    def _make_api_request(self, xml_payload):
        """Make API request to Nexterus"""
        params = {
            'page': 'login',
            'serviceType': 'RequestShipment',
            'action': 'TBBWebService'
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # Prepare form data
        form_data = {
            'RequestShipment': xml_payload
        }

        try:
            # Build full URL for logging
            full_url = f"{self.url}?{urlencode(params)}"

            _logger.info("=" * 60)
            _logger.info("NEXTERUS API REQUEST")
            _logger.info("=" * 60)
            _logger.info("URL: %s", self.url)
            _logger.info("Full URL with params: %s", full_url)
            _logger.info("Environment: %s", "PRODUCTION" if self.carrier.prod_environment else "TEST")
            _logger.info("Username: %s", self.carrier.nexterus_username)
            _logger.info("=" * 60)

            response = self.session.post(
                self.url,
                params=params,
                data=urlencode(form_data),
                headers=headers,
                timeout=360
            )

            _logger.info("Response Status Code: %s", response.status_code)
            _logger.info("Response URL: %s", response.url)

            if response.status_code != 200:
                _logger.error("Error Response: %s", response.text)
                return {
                    'errors': [f"HTTP Error {response.status_code}: {response.text}"]
                }

            # Extract XML from response
            response_text = response.text
            if 'RequestShipment=' in response_text:
                response_text = response_text.split('RequestShipment=')[1]

            return self._parse_xml_response(response_text)

        except requests.exceptions.ConnectionError as e:
            _logger.error(f"Connection Error: {e}")
            return {'errors': ["Cannot reach Nexterus server. Please try again later."]}
        except Exception as e:
            _logger.error(f"Unexpected error: {e}")
            return {'errors': [str(e)]}

    def get_rates(self, order, package_types):
        """Get shipping rates from Nexterus"""
        shipment_data = self._prepare_rate_request(order, package_types)
        xml_request = self._build_xml_request(shipment_data)

        _logger.info("Nexterus Rate Request XML:\n%s", xml_request)

        response = self._make_api_request(xml_request)

        _logger.info("Nexterus Rate Response: %s", response)

        if response.get('errors'):
            error_msg = '\n'.join(response['errors'])
            raise ValidationError(f"Nexterus Error: {error_msg}")

        return response

    def _prepare_rate_request(self, order, package_types):
        """Prepare data for rate request"""
        warehouse = order.warehouse_id if hasattr(order, 'warehouse_id') else order.picking_type_id.warehouse_id
        partner = order.partner_shipping_id if hasattr(order, 'partner_shipping_id') else order.partner_id

        # Calculate ship date - ensure it's in the future
        from datetime import datetime, timedelta
        ship_date = datetime.now() + timedelta(days=1)

        # Format phone numbers properly
        shipper_phone = self._format_phone(warehouse.partner_id.phone) if warehouse.partner_id.phone else "864-678-6953"
        consignee_phone = self._format_phone(partner.phone) if partner.phone else "000-000-0000"

        shipment_data = {
            'header': {
                'RequestType': 'Add',
                'ServiceType': 'LTL',
                'ShipmentMethod': 'LTL',
                'ScheduleShipment': 'N',
                'GenerateRates': 'Y',
                'AutoSelectCarrier': 'N',
                'GeneratePRONumber': 'N',
                'CallCarrierForPickup': 'N',
                'PersonCalling': 'SPAN',  # Or warehouse.partner_id.name[:50] if it exists
                'Prepaid': 'Y',
                'FreightDirection': 'OUTBOUND',
                'ShipDate': ship_date.strftime('%m/%d/%Y'),
                'TimeShipperCloses': '19:00',
                'TimeFreightReady': '17:00',  # Changed from 08:00 to match your test
            },
            'accessorials': {},
            'address': {
                'shipper': {
                    'SiteType': 'Business',
                    'Name': (warehouse.partner_id.name or 'SPAN')[:50],  # Limit length
                    'Street': (warehouse.partner_id.street or '70 COMMERCE CENTER').upper(),
                    'City': warehouse.partner_id.city or 'Greenville',
                    'StateCode': warehouse.partner_id.state_id.code if warehouse.partner_id.state_id else 'SC',
                    'CountryCode': warehouse.partner_id.country_id.code if warehouse.partner_id.country_id else 'US',
                    'PostalCode': warehouse.partner_id.zip or '29615',
                    'ContactName': 'Shipping',  # Simple default
                    'ContactPhone': shipper_phone,
                },
                'consignee': {
                    'SiteType': 'Business' if partner.is_company else 'Residential',
                    'Name': partner.name[:50] if partner.name else 'Recipient',
                    'Street': (partner.street or '').upper(),
                    'City': partner.city or '',
                    'StateCode': partner.state_id.code if partner.state_id else '',
                    'CountryCode': partner.country_id.code if partner.country_id else 'US',
                    'PostalCode': partner.zip or '',
                    'ContactName': partner.name[:50] if partner.name else 'Recipient',
                    'ContactPhone': consignee_phone,
                }
            },
            'commodities': []
        }

        # Add accessorials based on configuration
        if self.carrier.nexterus_liftgate_origin:
            shipment_data['accessorials']['OriginLiftgate'] = 'Y'
        if self.carrier.nexterus_liftgate_destination:
            shipment_data['accessorials']['DestinationLiftgate'] = 'Y'
        if self.carrier.nexterus_inside_delivery:
            shipment_data['accessorials']['InsideDelivery'] = 'Y'
        if self.carrier.nexterus_notification_required:
            shipment_data['accessorials']['NotificationRequired'] = 'Y'
        if not partner.is_company:
            shipment_data['accessorials']['ResidentialDelivery'] = 'Y'

        # If no accessorials, add at least NotificationRequired as in your test
        if not shipment_data['accessorials']:
            shipment_data['accessorials']['NotificationRequired'] = 'Y'
            shipment_data['accessorials']['InsideDelivery'] = 'N'

        # Build commodities from package types
        for package in package_types:
            # Handle both dictionary and object formats
            if isinstance(package, dict):
                # Package is a dictionary from the wizard
                package_type = package.get('package_type')
                qty = package.get('qty', 1)
                total_weight = package.get('total_weight', package.get('weight', 200))
                weight = package.get('weight', 200)
                depth = package.get('depth')
                width = package.get('width')
                height = package.get('height')
            else:
                # Package is an object
                package_type = getattr(package, 'package_type', None)
                qty = getattr(package, 'qty', 1)
                total_weight = getattr(package, 'total_weight', None) or getattr(package, 'weight', 200)
                weight = getattr(package, 'weight', 200)
                depth = getattr(package, 'depth', None)
                width = getattr(package, 'width', None)
                height = getattr(package, 'height', None)

            # Determine piece type from package type name
            piece_type = 'SKID'  # Default
            if package_type:
                pkg_name = package_type.name.upper() if hasattr(package_type, 'name') else str(package_type).upper()
                if 'PALLET' in pkg_name:
                    piece_type = 'PALLET'
                elif 'SKID' in pkg_name:
                    piece_type = 'SKID'
                elif 'CRATE' in pkg_name:
                    piece_type = 'CRATE'
                elif 'BOX' in pkg_name or 'CARTON' in pkg_name:
                    piece_type = 'CARTONS'
                elif 'DRUM' in pkg_name:
                    piece_type = 'DRUM'

            commodity = {
                'CommodityName': 'SKIDS',
                'NumberOfSkids': str(qty),
                'NumberOfPieces': str(qty),
                'PieceType': piece_type,
                'UnitOfWeight': 'POUNDS',
                'Weight': str(int(total_weight or weight)),
                'ClassNumber': str(self._get_freight_class(package)),
                'UnitOfMeasure': 'INCHES',
            }

            # Add dimensions - use defaults if not provided
            if depth and width and height:
                commodity.update({
                    'Length': str(int(depth)),
                    'Width': str(int(width)),
                    'Height': str(int(height)),
                })
            else:
                # Default pallet dimensions
                commodity.update({
                    'Length': '48',
                    'Width': '40',
                    'Height': '60',
                })

            shipment_data['commodities'].append(commodity)

        return shipment_data

    def _validate_shipment_data(self, shipment_data):
        """Validate shipment data before sending"""
        errors = []

        # Check shipper address
        shipper = shipment_data.get('address', {}).get('shipper', {})
        if not shipper.get('Street'):
            errors.append("Shipper street address is required")
        if not shipper.get('City'):
            errors.append("Shipper city is required")
        if not shipper.get('PostalCode'):
            errors.append("Shipper postal code is required")

        # Check consignee address
        consignee = shipment_data.get('address', {}).get('consignee', {})
        if not consignee.get('Street'):
            errors.append("Consignee street address is required")
        if not consignee.get('City'):
            errors.append("Consignee city is required")
        if not consignee.get('PostalCode'):
            errors.append("Consignee postal code is required")

        # Check commodities
        if not shipment_data.get('commodities'):
            errors.append("At least one commodity is required")
        else:
            for idx, commodity in enumerate(shipment_data['commodities']):
                if not commodity.get('Weight') or float(commodity.get('Weight', 0)) <= 0:
                    errors.append(f"Commodity {idx + 1}: Weight must be greater than 0")
                if not commodity.get('ClassNumber'):
                    errors.append(f"Commodity {idx + 1}: Freight class is required")

        if errors:
            raise ValidationError('\n'.join(errors))


    def create_shipment(self, order, selected_carrier_scac, quote_id):
        """Create and schedule a shipment with selected carrier"""
        """Create and schedule a shipment with selected carrier"""

        _logger.info("=== CREATE SHIPMENT ===")
        _logger.info("Using quote ID: %s", quote_id)
        _logger.info("Selected carrier: %s", selected_carrier_scac)

        # We need to rebuild the full shipment data, not just the header
        # First, get the original shipment data structure
        warehouse = order.warehouse_id if hasattr(order, 'warehouse_id') else order.picking_type_id.warehouse_id
        partner = order.partner_shipping_id if hasattr(order, 'partner_shipping_id') else order.partner_id

        # Format phone numbers
        shipper_phone = self._format_phone(warehouse.partner_id.phone) if warehouse.partner_id.phone else "864-678-6953"
        consignee_phone = self._format_phone(partner.phone) if partner.phone else "000-000-0000"

        from datetime import datetime, timedelta
        ship_date = datetime.now() + timedelta(days=1)

        shipment_data = {
            'header': {
                'RequestType': 'Update',  # This is UPDATE, not Add
                'ServiceType': 'LTL',
                'ShipmentMethod': 'LTL',
                'SourceReferenceNumber': quote_id,  # This is critical
                'SelectedCarrier': selected_carrier_scac,  # Selected carrier SCAC
                'ScheduleShipment': 'Y',  # Schedule the shipment
                'GenerateRates': 'N',  # Don't regenerate rates
                'AutoSelectCarrier': 'N',
                'GeneratePRONumber': 'Y',  # Generate PRO number
                'CallCarrierForPickup': 'Y' if self.carrier.nexterus_call_for_pickup else 'N',
                'PersonCalling': 'SPAN',
                'Prepaid': 'Y',
                'FreightDirection': 'OUTBOUND',
                'ShipDate': ship_date.strftime('%m/%d/%Y'),
                'TimeShipperCloses': '19:00',
                'TimeFreightReady': '17:00',
            },
            'accessorials': {},
            'address': {
                'shipper': {
                    'SiteType': 'Business',
                    'Name': (warehouse.partner_id.name or 'SPAN')[:50],
                    'Street': (warehouse.partner_id.street or '70 COMMERCE CENTER').upper(),
                    'City': warehouse.partner_id.city or 'Greenville',
                    'StateCode': warehouse.partner_id.state_id.code if warehouse.partner_id.state_id else 'SC',
                    'CountryCode': warehouse.partner_id.country_id.code if warehouse.partner_id.country_id else 'US',
                    'PostalCode': warehouse.partner_id.zip or '29615',
                    'ContactName': 'Shipping',
                    'ContactPhone': shipper_phone,
                },
                'consignee': {
                    'SiteType': 'Business' if partner.is_company else 'Residential',
                    'Name': partner.name[:50] if partner.name else 'Recipient',
                    'Street': (partner.street or '').upper(),
                    'City': partner.city or '',
                    'StateCode': partner.state_id.code if partner.state_id else '',
                    'CountryCode': partner.country_id.code if partner.country_id else 'US',
                    'PostalCode': partner.zip or '',
                    'ContactName': partner.name[:50] if partner.name else 'Recipient',
                    'ContactPhone': consignee_phone,
                }
            },
            'commodities': []
        }

        # Add accessorials
        if self.carrier.nexterus_notification_required:
            shipment_data['accessorials']['NotificationRequired'] = 'Y'
        if self.carrier.nexterus_inside_delivery:
            shipment_data['accessorials']['InsideDelivery'] = 'Y'
        else:
            shipment_data['accessorials']['InsideDelivery'] = 'N'
        if not partner.is_company:
            shipment_data['accessorials']['ResidentialDelivery'] = 'Y'

        # Add commodities from stored package types
        if hasattr(order, 'package_types') and order.package_types:
            for package in order.package_types:
                # Determine piece type
                piece_type = 'SKID'
                if package.package_type:
                    pkg_name = package.package_type.name.upper()
                    if 'PALLET' in pkg_name:
                        piece_type = 'PALLET'
                    elif 'SKID' in pkg_name:
                        piece_type = 'SKID'
                    elif 'CRATE' in pkg_name:
                        piece_type = 'CRATE'
                    elif 'BOX' in pkg_name or 'CARTON' in pkg_name:
                        piece_type = 'CARTONS'

                weight = max(float(package.total_weight or package.weight or 150), 150)

                commodity = {
                    'CommodityName': 'GENERAL FREIGHT',
                    'NumberOfSkids': str(package.qty or 1),
                    'NumberOfPieces': str(package.qty or 1),
                    'PieceType': piece_type,
                    'UnitOfWeight': 'POUNDS',
                    'Weight': str(int(weight)),
                    'ClassNumber': str(self.carrier.nexterus_default_freight_class or '85'),
                    'UnitOfMeasure': 'INCHES',
                }

                # Add dimensions
                if package.depth and package.width and package.height:
                    commodity.update({
                        'Length': str(int(package.depth)),
                        'Width': str(int(package.width)),
                        'Height': str(int(package.height)),
                    })
                else:
                    commodity.update({
                        'Length': '48',
                        'Width': '40',
                        'Height': '48',
                    })

                shipment_data['commodities'].append(commodity)
        else:
            # Default commodity if no packages stored
            shipment_data['commodities'].append({
                'CommodityName': 'GENERAL FREIGHT',
                'NumberOfSkids': '1',
                'NumberOfPieces': '1',
                'PieceType': 'PALLET',
                'UnitOfWeight': 'POUNDS',
                'Weight': '200',
                'ClassNumber': str(self.carrier.nexterus_default_freight_class or '85'),
                'UnitOfMeasure': 'INCHES',
                'Length': '48',
                'Width': '40',
                'Height': '48',
            })

        _logger.info("Creating shipment with quote ID: %s and carrier: %s", quote_id, selected_carrier_scac)

        xml_request = self._build_xml_request(shipment_data)
        _logger.info("Nexterus Create Shipment Request XML:\n%s", xml_request)

        response = self._make_api_request(xml_request)
        _logger.info("Nexterus Create Shipment Response: %s", response)

        if response.get('errors'):
            error_msg = '\n'.join(response['errors'])
            raise ValidationError(f"Nexterus Error: {error_msg}")

        return response

    def _format_phone(self, phone):
        """Format phone number to XXX-XXX-XXXX format"""
        if not phone:
            return '000-000-0000'

        # Remove all non-numeric characters
        phone_digits = ''.join(filter(str.isdigit, phone))

        if len(phone_digits) >= 10:
            return f"{phone_digits[:3]}-{phone_digits[3:6]}-{phone_digits[6:10]}"
        else:
            return '000-000-0000'

    def _get_freight_class(self, package):
        """Get freight class from package or product"""
        # Try to get from product first
        if hasattr(package, 'product_id') and package.product_id:
            if hasattr(package.product_id, 'freight_class') and package.product_id.freight_class:
                return package.product_id.freight_class

        # Default freight class if not specified
        return self.carrier.nexterus_default_freight_class or '85'