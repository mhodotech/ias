# -*- coding: utf-8 -*-
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urlencode

from odoo import fields, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class NexterusRequest:
    """Handle communication with Nexterus API"""

    def __init__(self, carrier):
        """Initialize Nexterus API handler"""
        self.carrier = carrier
        if carrier.prod_environment:
            self.url = 'https://fusioncenter.nexterus.com/FusionCenter/ws'
        else:
            self.url = 'https://test.nexterus.com/FusionCenter/ws'

        self.session = requests.Session()
        self.session.auth = (carrier.nexterus_username, carrier.nexterus_password)

    def get_rates(self, packages, partner_shipping, warehouse, special_services=None):
        """Get rates from Nexterus for given packages"""
        shipment_data = self._prepare_rate_request(packages, partner_shipping, warehouse, special_services)
        xml_request = self._build_xml_request(shipment_data)

        _logger.info("Nexterus Rate Request XML:\n%s", xml_request)

        response = self._make_api_request(xml_request)

        if response.get('errors'):
            error_msg = '\n'.join(response['errors'])
            raise ValidationError(f"Nexterus Error: {error_msg}")

        return response

    def create_shipment(self, quote_id, carrier_scac, packages, partner_shipping, warehouse, special_services=None):
        """Create shipment in Nexterus"""
        shipment_data = self._prepare_shipment_request(
            quote_id, carrier_scac, packages, partner_shipping, warehouse, special_services
        )
        xml_request = self._build_xml_request(shipment_data)

        _logger.info("Nexterus Create Shipment Request XML:\n%s", xml_request)

        response = self._make_api_request(xml_request)

        if response.get('errors'):
            error_msg = '\n'.join(response['errors'])
            raise ValidationError(f"Nexterus Error: {error_msg}")

        return response

    def _prepare_rate_request(self, packages, partner_shipping, warehouse, special_services=None):
        """Prepare data for rate request"""
        if special_services is None:
            special_services = {}

        ship_date = datetime.now() + timedelta(days=1)

        # Convert times to HH:MM format
        close_time = "{:02d}:{:02d}".format(
            int(self.carrier.nexterus_close_time),
            int((self.carrier.nexterus_close_time % 1) * 60)
        )
        ready_time = "{:02d}:{:02d}".format(
            int(self.carrier.nexterus_ready_time),
            int((self.carrier.nexterus_ready_time % 1) * 60)
        )

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
                'PersonCalling': 'Span America',
                'Prepaid': 'Y',
                'FreightDirection': 'OUTBOUND',
                'ShipDate': ship_date.strftime('%m/%d/%Y'),
                'TimeShipperCloses': close_time,
                'TimeFreightReady': ready_time,
            },
            'accessorials': {},
            'address': {
                'shipper': self._get_shipper_address(warehouse),
                'consignee': self._get_consignee_address(partner_shipping)
            },
            'commodities': self._build_commodities(packages)
        }

        # Add accessorials based on special services
        if special_services.get('liftgate') or partner_shipping.default_requires_liftgate:
            shipment_data['accessorials']['DestinationLiftgate'] = 'Y'

        if special_services.get('inside_delivery') or partner_shipping.default_requires_inside_delivery:
            shipment_data['accessorials']['InsideDelivery'] = 'Y'

        if not partner_shipping.is_company:
            shipment_data['accessorials']['ResidentialDelivery'] = 'Y'

        # Default notification
        shipment_data['accessorials']['NotificationRequired'] = 'Y'

        return shipment_data

    def _prepare_shipment_request(self, quote_id, carrier_scac, packages, partner_shipping, warehouse,
                                  special_services=None):
        """Prepare data for shipment creation"""
        shipment_data = self._prepare_rate_request(packages, partner_shipping, warehouse, special_services)

        # Update for shipment creation
        shipment_data['header'].update({
            'RequestType': 'Update',
            'SourceReferenceNumber': quote_id,
            'SelectedCarrier': carrier_scac,
            'ScheduleShipment': 'Y',
            'GenerateRates': 'N',
            'GeneratePRONumber': 'Y',
        })

        return shipment_data

    def _get_shipper_address(self, warehouse):
        """Build shipper address dict"""
        partner = warehouse.partner_id
        return {
            'SiteType': 'Business',
            'Name': (partner.name or 'Span America')[:50],
            'Street': (partner.street or '70 Commerce Center').upper(),
            'City': partner.city or 'Greenville',
            'StateCode': partner.state_id.code if partner.state_id else 'SC',
            'CountryCode': partner.country_id.code if partner.country_id else 'US',
            'PostalCode': partner.zip or '29615',
            'ContactName': 'Shipping',
            'ContactPhone': self._format_phone(partner.phone) if partner.phone else '864-678-6953',
        }

    def _get_consignee_address(self, partner):
        """Build consignee address dict"""
        return {
            'SiteType': 'Business' if partner.is_company else 'Residential',
            'Name': (partner.name or 'Customer')[:50],
            'Street': (partner.street or '').upper(),
            'City': partner.city or '',
            'StateCode': partner.state_id.code if partner.state_id else '',
            'CountryCode': partner.country_id.code if partner.country_id else 'US',
            'PostalCode': partner.zip or '',
            'ContactName': (partner.name or 'Customer')[:50],
            'ContactPhone': self._format_phone(partner.phone) if partner.phone else '000-000-0000',
        }

    def _build_commodities(self, packages):
        """Build commodity list from packages"""
        commodities = []

        for package in packages:
            # Determine piece type from span package type
            piece_type = 'SKID'
            if package.span_package_type_id:
                piece_type = package.span_package_type_id.code
            elif package.package_type_id and 'pallet' in package.package_type_id.name.lower():
                piece_type = 'PALLET'

            commodity_name = 'General Freight'
            if package.commodity_description_id:
                commodity_name = package.commodity_description_id.name
            elif package.package_type_id:
                commodity_name = package.package_type_id.name

            commodity = {
                'CommodityName': commodity_name[:50],
                'NumberOfSkids': '1',
                'PieceType': piece_type,
                'NumberOfPieces': str(package.span_package_qty or 1),
                'UnitOfWeight': 'POUNDS',
                'Weight': str(int(package.shipping_weight or 100)),
                'ClassNumber': package.nmfc_class or '85',
                'UnitOfMeasure': 'INCHES',
            }

            # Add dimensions if available
            if all([package.shipping_length, package.shipping_width, package.shipping_height]):
                commodity.update({
                    'Length': str(int(package.shipping_length)),
                    'Width': str(int(package.shipping_width)),
                    'Height': str(int(package.shipping_height)),
                })

            # Add NMFC code if available
            if package.nmfc_code:
                commodity['ClientProductCode'] = package.nmfc_code

            commodities.append(commodity)

        return commodities

    def _format_phone(self, phone):
        """Format phone to XXX-XXX-XXXX"""
        if not phone:
            return '000-000-0000'

        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) >= 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:10]}"
        return '000-000-0000'

    def _build_xml_request(self, shipment_data):
        """Build XML request for Nexterus"""
        root = ET.Element("TBB")
        if self.carrier.prod_environment:
            root.set("xmlns", "http://www.fusioncenter.nexterus.com/RequestShipment/LTL/v3")
        else:
            root.set("xmlns", "http://www.test.nexterus.com/RequestShipment/LTL/v3")

        shipment = ET.SubElement(root, "Shipment")

        # Build Header
        header = ET.SubElement(shipment, "Header")
        for key, value in shipment_data.get('header', {}).items():
            if value is not None:
                ET.SubElement(header, key).text = str(value)

        # Build Accessorials
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
                    if value:
                        ET.SubElement(shipper, key).text = str(value)

            # Consignee
            if shipment_data['address'].get('consignee'):
                consignee = ET.SubElement(address, "Consignee")
                for key, value in shipment_data['address']['consignee'].items():
                    if value:
                        ET.SubElement(consignee, key).text = str(value)

        # Build Commodities
        if shipment_data.get('commodities'):
            commodities = ET.SubElement(shipment, "Commodities")
            for commodity_data in shipment_data['commodities']:
                commodity = ET.SubElement(commodities, "Commodity")
                for key, value in commodity_data.items():
                    if value is not None:
                        ET.SubElement(commodity, key).text = str(value)

        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_str += ET.tostring(root, encoding='unicode')
        return xml_str

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

        form_data = {
            'RequestShipment': xml_payload
        }

        try:
            response = self.session.post(
                self.url,
                params=params,
                data=urlencode(form_data),
                headers=headers,
                timeout=960
            )

            if response.status_code != 200:
                return {
                    'errors': [f"HTTP Error {response.status_code}: {response.text}"]
                }

            response_text = response.text
            if 'RequestShipment=' in response_text:
                response_text = response_text.split('RequestShipment=')[1]

            return self._parse_xml_response(response_text)

        except requests.exceptions.ConnectionError as e:
            return {'errors': ["Cannot reach Nexterus server. Please try again later."]}
        except Exception as e:
            return {'errors': [str(e)]}

    def _parse_xml_response(self, xml_string):
        """Parse XML response from Nexterus"""
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
                # Get quote ID
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

                # Parse PRO number
                pro_number = response.find('PRONumber')
                if pro_number is not None:
                    response_data['pro_number'] = pro_number.text

            # Parse errors
            errors = root.findall('.//Error')
            if errors:
                response_data['errors'] = [error.text for error in errors]

            return response_data

        except ET.ParseError as e:
            return {'errors': [f"Failed to parse response: {str(e)}"]}