from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    gp_custnmbr = fields.Char(
        'GP Customer Number',
        index=True,
        help='Customer number from GP (CUSTNMBR)'
    )
    gp_custname = fields.Char(
        'GP Customer Name',
        help='Original customer name from GP'
    )
    gp_adrscode = fields.Char(
        'GP Address Code',
        help='Address code from GP (ADRSCODE) - e.g., PRIMARY, BILL-TO, SHIP-TO'
    )
    gp_prclevel = fields.Char(
        'GP Price Level',
        help='Customer price level from GP'
    )
    gp_custclas = fields.Char(
        'GP Customer Class',
        help='Customer class from GP'
    )
    gp_last_sync = fields.Datetime(
        'Last GP Sync',
        help='Last synchronization with GP'
    )

    @api.model
    def find_or_create_from_gp(self, gp_data):
        """Find or create partner from GP data with proper address handling"""
        customer_number = str(gp_data.get('CUSTNMBR', '')).strip()

        # Search for main customer (parent)
        partner = self.search([
            ('gp_custnmbr', '=', customer_number),
            ('parent_id', '=', False)
        ], limit=1)

        if not partner:
            # Check if auto-create is enabled
            config = self.env['gp.config'].search([('active', '=', True)], limit=1)
            if not config or not config.auto_create_customers:
                # Try to find by name as fallback
                customer_name = gp_data.get('CUSTNAME', '').strip()
                partner = self.search([
                    ('name', '=', customer_name),
                    ('parent_id', '=', False)
                ], limit=1)
                if not partner:
                    raise ValidationError(f'Customer {customer_number} not found and auto-create is disabled')
            else:
                # Create new partner with main address
                partner = self._create_partner_from_gp(gp_data)
        else:
            # Update existing partner if needed
            self._update_partner_from_gp(partner, gp_data)

        # Handle shipping address if different
        if gp_data.get('ShipToName') and gp_data.get('ADDRESS1'):
            shipping_partner = self._ensure_shipping_address(partner, gp_data)
            return shipping_partner or partner

        return partner

    def _create_partner_from_gp(self, gp_data):
        """Create new partner from GP data"""
        customer_number = str(gp_data.get('CUSTNMBR', '')).strip()
        customer_name = gp_data.get('CUSTNAME', customer_number).strip()

        vals = {
            'name': customer_name,
            'gp_custnmbr': customer_number,
            'gp_custname': customer_name,
            'is_company': True,
            'customer_rank': 1,
            'gp_last_sync': fields.Datetime.now(),
        }

        # Add main address if available
        if gp_data.get('ADDRESS1'):
            vals.update({
                'street': gp_data.get('ADDRESS1', '').strip(),
                'street2': gp_data.get('ADDRESS2', '').strip() if gp_data.get('ADDRESS2') else '',
                'city': gp_data.get('CITY', '').strip(),
                'state_id': self._get_state_id(gp_data.get('STATE', '')),
                'zip': str(gp_data.get('ZIP', '') or gp_data.get('ZIPCODE', '')).strip(),
                'country_id': self._get_country_id(gp_data.get('COUNTRY', 'US')),
                'phone': self._format_phone(gp_data.get('PHONE1') or gp_data.get('PHNUMBR1')),
            })

        # Add GP specific fields
        if gp_data.get('PRCLEVEL'):
            vals['gp_prclevel'] = str(gp_data.get('PRCLEVEL')).strip()
        if gp_data.get('CUSTCLAS'):
            vals['gp_custclas'] = str(gp_data.get('CUSTCLAS')).strip()

        partner = self.create(vals)
        _logger.info(f'Created new partner: {customer_number} - {customer_name}')

        return partner

    def _update_partner_from_gp(self, partner, gp_data):
        """Update existing partner from GP data"""
        vals = {
            'gp_last_sync': fields.Datetime.now(),
        }

        # Only update if significantly different
        if gp_data.get('CUSTNAME'):
            new_name = gp_data.get('CUSTNAME', '').strip()
            if new_name and new_name != partner.name and not partner.child_ids:
                vals['name'] = new_name

        if vals and len(vals) > 1:  # More than just sync date
            partner.write(vals)

    def _ensure_shipping_address(self, partner, gp_data):
        """Ensure shipping address exists as child contact"""
        # Build unique key for shipping address
        ship_to_name = gp_data.get('ShipToName', '').strip()
        address1 = gp_data.get('ADDRESS1', '').strip()
        city = gp_data.get('CITY', '').strip()

        if not ship_to_name or not address1:
            return None

        # Search for existing shipping address
        shipping_partner = self.search([
            ('parent_id', '=', partner.id),
            ('type', '=', 'delivery'),
            '|',
            ('name', '=', ship_to_name),
            '&',
            ('street', '=', address1),
            ('city', '=', city)
        ], limit=1)

        if not shipping_partner:
            # Create shipping address
            shipping_vals = {
                'parent_id': partner.id,
                'name': ship_to_name,
                'type': 'delivery',
                'street': address1,
                'street2': gp_data.get('ADDRESS2', '').strip() if gp_data.get('ADDRESS2') else '',
                'city': city,
                'state_id': self._get_state_id(gp_data.get('STATE', '')),
                'zip': str(gp_data.get('ZIPCODE', '') or gp_data.get('ZIP', '')).strip(),
                'country_id': self._get_country_id(gp_data.get('COUNTRY', 'US')),
                'phone': self._format_phone(gp_data.get('PHONE1') or gp_data.get('PHNUMBR1')),
                'gp_custnmbr': partner.gp_custnmbr,
                'gp_adrscode': gp_data.get('PRSTADCD', 'SHIP-TO'),  # Ship-to address code
            }

            if gp_data.get('CNTCPRSN'):
                shipping_vals['name'] = f"{ship_to_name} - {gp_data.get('CNTCPRSN', '').strip()}"

            shipping_partner = self.create(shipping_vals)
            _logger.info(f'Created shipping address for {partner.name}: {ship_to_name}')

        return shipping_partner

    def _get_state_id(self, state_code):
        """Get state ID from code"""
        if not state_code:
            return False
        state_code = str(state_code).strip()
        if not state_code:
            return False
        state = self.env['res.country.state'].search([
            ('code', '=', state_code),
            ('country_id.code', '=', 'US')
        ], limit=1)
        return state.id if state else False

    def _get_country_id(self, country_code):
        """Get country ID from code"""
        if not country_code:
            country_code = 'US'
        country_code = str(country_code).strip() or 'US'
        country = self.env['res.country'].search([
            ('code', '=', country_code)
        ], limit=1)
        if not country:
            country = self.env['res.country'].search([
                ('code', '=', 'US')
            ], limit=1)
        return country.id if country else False

    def _format_phone(self, phone):
        """Format phone number"""
        if not phone:
            return ''
        phone_str = str(phone).strip()
        # Remove decimals if present
        if '.' in phone_str:
            phone_str = phone_str.split('.')[0]
        # Basic formatting
        if len(phone_str) == 10 and phone_str.isdigit():
            return f"({phone_str[:3]}) {phone_str[3:6]}-{phone_str[6:]}"
        return phone_str

    def sync_from_gp(self):
        """Action to sync this specific customer from GP"""
        self.ensure_one()

        if not self.gp_custnmbr:
            raise ValidationError('This partner does not have a GP customer number')

        if self.parent_id:
            raise ValidationError('Please sync from the main customer record, not the contact')

        config = self.env['gp.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise ValidationError('No active GP configuration found')

        try:
            import pyodbc
            conn = pyodbc.connect(config.get_connection_string())
            cursor = conn.cursor()

            # Fetch customer master data
            query = """
                SELECT 
                    CUSTNMBR,
                    CUSTNAME,
                    CUSTCLAS,
                    PRCLEVEL,
                    ADDRESS1,
                    ADDRESS2,
                    ADDRESS3,
                    CITY,
                    STATE,
                    ZIP,
                    COUNTRY,
                    PHONE1,
                    FAX,
                    CNTCPRSN,
                    TAXSCHID,
                    SLPRSNID,
                    SALSTERR
                FROM RM00101
                WHERE CUSTNMBR = ?
            """

            cursor.execute(query, self.gp_custnmbr)
            columns = [column[0] for column in cursor.description]
            row = cursor.fetchone()

            if row:
                customer_data = dict(zip(columns, row))
                # Convert CUSTNMBR to string
                customer_data['CUSTNMBR'] = str(customer_data['CUSTNMBR'])

                # Update main customer
                self._update_partner_from_gp(self, customer_data)

                # Fetch and sync addresses from RM00102
                self._sync_customer_addresses(cursor)

                message = f'Customer {self.gp_custnmbr} synced successfully from GP'
            else:
                message = f'Customer {self.gp_custnmbr} not found in GP'

            cursor.close()
            conn.close()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Complete',
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            raise UserError(f'Error syncing from GP: {str(e)}')

    def _sync_customer_addresses(self, cursor):
        """Sync all addresses for this customer from RM00102"""
        query = """
            SELECT 
                ADRSCODE,
                ShipToName,
                CNTCPRSN,
                ADDRESS1,
                ADDRESS2,
                ADDRESS3,
                CITY,
                STATE,
                ZIP,
                COUNTRY,
                PHONE1,
                SHIPMTHD,
                TAXSCHID
            FROM RM00102
            WHERE CUSTNMBR = ?
            ORDER BY ADRSCODE
        """

        cursor.execute(query, self.gp_custnmbr)
        columns = [column[0] for column in cursor.description]

        for row in cursor.fetchall():
            address_data = dict(zip(columns, row))

            # Skip empty addresses
            if not address_data.get('ADDRESS1'):
                continue

            adrscode = str(address_data.get('ADRSCODE', '')).strip()

            # Determine address type
            address_type = 'delivery'
            if 'BILL' in adrscode.upper():
                address_type = 'invoice'
            elif 'MAIN' in adrscode.upper() or 'PRIMARY' in adrscode.upper():
                address_type = 'contact'

            # Search for existing address
            existing = self.search([
                ('parent_id', '=', self.id),
                ('gp_adrscode', '=', adrscode)
            ], limit=1)

            address_vals = {
                'name': address_data.get('ShipToName', '').strip() or f"{self.name} - {adrscode}",
                'type': address_type,
                'street': address_data.get('ADDRESS1', '').strip(),
                'street2': address_data.get('ADDRESS2', '').strip() if address_data.get('ADDRESS2') else '',
                'city': address_data.get('CITY', '').strip(),
                'state_id': self._get_state_id(address_data.get('STATE')),
                'zip': str(address_data.get('ZIP', '')).strip(),
                'country_id': self._get_country_id(address_data.get('COUNTRY')),
                'phone': self._format_phone(address_data.get('PHONE1')),
                'gp_adrscode': adrscode,
                'gp_custnmbr': self.gp_custnmbr,
            }

            if existing:
                existing.write(address_vals)
                _logger.info(f'Updated address {adrscode} for customer {self.gp_custnmbr}')
            else:
                address_vals['parent_id'] = self.id
                self.create(address_vals)
                _logger.info(f'Created address {adrscode} for customer {self.gp_custnmbr}')