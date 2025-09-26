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

    @api.model
    def find_or_create_from_gp(self, gp_data):
        """Find or create partner from GP data"""
        customer_number = gp_data.get('CUSTNMBR', '').strip()

        # Search existing partner
        partner = self.search([('gp_custnmbr', '=', customer_number)], limit=1)

        if not partner:
            # Check if auto-create is enabled
            config = self.env['gp.config'].search([('active', '=', True)], limit=1)
            if not config or not config.auto_create_customers:
                # Try to find by name as fallback
                customer_name = gp_data.get('CUSTNAME', '').strip()
                partner = self.search([('name', '=', customer_name)], limit=1)
                if not partner:
                    raise ValidationError(f'Customer {customer_number} not found and auto-create is disabled')
            else:
                # Create new partner
                vals = {
                    'name': gp_data.get('CUSTNAME', customer_number).strip(),
                    'gp_custnmbr': customer_number,
                    'gp_custname': gp_data.get('CUSTNAME', '').strip(),
                    'is_company': True,
                    'customer_rank': 1,
                }

                # Add address if available
                if gp_data.get('ShipToName'):
                    vals['street'] = gp_data.get('ADDRESS1', '').strip()
                    vals['street2'] = gp_data.get('ADDRESS2', '').strip()
                    vals['city'] = gp_data.get('CITY', '').strip()
                    vals['state_id'] = self._get_state_id(gp_data.get('STATE', ''))
                    vals['zip'] = gp_data.get('ZIPCODE', '').strip()

                partner = self.create(vals)
                _logger.info(f'Created new partner: {customer_number}')

        return partner

    def _get_state_id(self, state_code):
        """Get state ID from code"""
        if not state_code:
            return False
        state = self.env['res.country.state'].search([
            ('code', '=', state_code.strip()),
            ('country_id.code', '=', 'US')
        ], limit=1)
        return state.id if state else False
