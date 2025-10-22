from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # GP Fields
    gp_sopnumbe = fields.Char(
        'GP Order Number',
        index=True,
        copy=False,
        help='SOPNUMBE from GP SOP10100'
    )
    gp_custnmbr = fields.Char(
        'GP Customer ID',
        help='CUSTNMBR from GP'
    )
    gp_cstponbr = fields.Char(
        'GP Customer PO',
        help='Customer Purchase Order Number from GP'
    )
    gp_pckslpno = fields.Char(
        'GP Picking Ticket',
        help='Picking Slip Number from GP'
    )
    gp_bachnumb = fields.Char(
        'GP Batch Number',
        help='Batch Number from GP'
    )
    gp_slprsnid = fields.Char(
        'GP Salesperson ID',
        help='Salesperson ID from GP'
    )
    gp_salesperson_name = fields.Char(
        'GP Salesperson Name',
        help='Salesperson name from GP'
    )
    gp_salsterr = fields.Char(
        'GP Sales Territory',
        help='Sales Territory from GP'
    )
    gp_shipmthd = fields.Char(
        'GP Shipping Method',
        help='Shipping Method from GP'
    )
    gp_docdate = fields.Datetime(
        'GP Document Date',
        help='Original document date from GP'
    )
    gp_reqshipdate = fields.Datetime(
        'GP Requested Ship Date',
        help='Requested ship date from GP'
    )
    gp_fufildat = fields.Datetime(
        'GP Fulfillment Date',
        help='Fulfillment date from GP'
    )
    gp_actlship = fields.Datetime(
        'GP Actual Ship Date',
        help='Actual ship date from GP'
    )

    # Sync tracking
    gp_last_sync = fields.Datetime(
        'Last GP Sync',
        help='Last synchronization with GP'
    )
    gp_sync_status = fields.Selection([
        ('pending', 'Pending Sync'),
        ('synced', 'Synced'),
        ('error', 'Sync Error'),
    ], string='GP Sync Status', default='pending')

    @api.model
    def create_from_gp(self, gp_data, line_data):
        """Create sale order from GP data - only creates SO and Pick operation"""
        # Check if order already exists
        existing_order = self.search([('gp_sopnumbe', '=', gp_data['SOPNUMBE'])], limit=1)

        if existing_order:
            return self.update_from_gp(existing_order, gp_data, line_data)

        # Find or create partner
        partner = self.env['res.partner'].find_or_create_from_gp(gp_data)

        # Prepare order values
        vals = {
            'partner_id': partner.id,
            'gp_sopnumbe': gp_data['SOPNUMBE'],
            'gp_custnmbr': gp_data['CUSTNMBR'],
            'gp_cstponbr': gp_data.get('CSTPONBR', ''),
            'gp_pckslpno': gp_data.get('PCKSLPNO', ''),
            'gp_bachnumb': gp_data.get('BACHNUMB', ''),
            'gp_slprsnid': gp_data.get('SLPRSNID', ''),
            'gp_salesperson_name': gp_data.get('salesperson_name', ''),
            'gp_salsterr': gp_data.get('SALSTERR', ''),
            'gp_shipmthd': gp_data.get('SHIPMTHD', ''),
            'gp_docdate': gp_data.get('DOCDATE'),
            'gp_reqshipdate': gp_data.get('ReqShipDate'),
            'gp_fufildat': gp_data.get('FUFILDAT'),
            'gp_actlship': gp_data.get('ACTLSHIP'),
            'date_order': gp_data.get('DOCDATE'),
            'gp_sync_status': 'synced',
            'gp_last_sync': fields.Datetime.now(),
            'client_order_ref': gp_data.get('CSTPONBR', ''),
        }

        # Create order
        order = self.create(vals)

        # Add order lines
        for line in line_data:
            self._create_order_line(order, line)

        # Confirm order to create Pick operation (and Pack, Ship)
        if gp_data.get('PCKSLPNO'):
            order.action_confirm()

            # Configure the Pick operation with GP data
            order._configure_pick_operation(gp_data, line_data)

        return order

    @api.model
    def update_from_gp(self, order, gp_data, line_data):
        """Update existing order from GP data"""
        vals = {
            'gp_last_sync': fields.Datetime.now(),
            'gp_sync_status': 'synced',
        }

        # Update GP tracking fields if they changed
        update_fields = {
            'gp_pckslpno': 'PCKSLPNO',
            'gp_bachnumb': 'BACHNUMB',
            'gp_fufildat': 'FUFILDAT',
            'gp_actlship': 'ACTLSHIP',
            'gp_cstponbr': 'CSTPONBR',
        }

        for odoo_field, gp_field in update_fields.items():
            if gp_field in gp_data and gp_data[gp_field]:
                vals[odoo_field] = gp_data[gp_field]

        order.write(vals)

        # Update order lines if needed
        for line_data_item in line_data:
            item_number = line_data_item.get('ITEMNMBR', '').strip()
            product = self.env['product.product'].search([
                ('gp_itemnmbr', '=', item_number)
            ], limit=1)

            if not product:
                product = self.env['product.product'].find_or_create_from_gp(line_data_item)

            # Check if line exists
            existing_line = order.order_line.filtered(
                lambda l: l.product_id == product
            )

            if not existing_line:
                self._create_order_line(order, line_data_item)

        # Confirm order if needed
        if gp_data.get('PCKSLPNO') and order.state == 'draft':
            order.action_confirm()

        # Configure or update Pick operation
        if order.state in ['sale', 'done'] and gp_data.get('PCKSLPNO'):
            order._configure_pick_operation(gp_data, line_data)

        return order

    def _configure_pick_operation(self, gp_data, line_data):
        """Configure ONLY the Pick operation with GP data"""
        self.ensure_one()

        gp_pckslpno = gp_data.get('PCKSLPNO', '').strip()
        if not gp_pckslpno:
            return

        # Find the Pick operation (internal transfer from Stock to Packing)
        # In 3-step: WH/Stock → WH/Packing → WH/Output → Customer
        pick_operation = self.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'internal' and
                      p.state not in ['done', 'cancel'] and
                      'Pick' in (p.picking_type_id.name or '')
        )

        if not pick_operation:
            _logger.warning(f'No Pick operation found for order {self.name}')
            return

        # Should be only one Pick operation
        if len(pick_operation) > 1:
            _logger.warning(f'Multiple Pick operations found for order {self.name}, using first one')
            pick_operation = pick_operation[0]

        # Update Pick operation with GP data
        pick_vals = {
            'name': gp_pckslpno,  # Set Pick operation name to GP picking ticket number
            'gp_pckslpno': gp_pckslpno,
            'gp_bachnumb': gp_data.get('BACHNUMB', ''),
            'scheduled_date': gp_data.get('FUFILDAT') or gp_data.get('ReqShipDate') or fields.Datetime.now(),
        }

        pick_operation.write(pick_vals)

        # Always just reserve quantities (set to Ready state)
        # User will validate after physical picking is done
        if pick_operation.state in ['confirmed', 'waiting']:
            pick_operation.action_assign()

        # Store GP fulfillment info on moves for reference
        if gp_data.get('has_fulfillment'):
            self._process_pick_fulfillment(pick_operation, gp_data, line_data)

        _logger.info(f'Configured Pick operation {pick_operation.name} for order {self.name}')

    def _process_pick_fulfillment(self, picking, gp_data, line_data):
        """Process Pick operation fulfillment based on GP data"""
        # Ensure picking is in correct state
        if picking.state in ['confirmed', 'waiting']:
            picking.action_assign()

        # Update move quantities based on GP fulfilled quantities
        for line in line_data:
            qty_fulfilled = line.get('QTYFULFI', 0)
            if qty_fulfilled > 0:
                item_number = line.get('ITEMNMBR', '').strip()
                product = self.env['product.product'].search([
                    ('gp_itemnmbr', '=', item_number)
                ], limit=1)

                if product:
                    move = picking.move_ids.filtered(
                        lambda m: m.product_id == product
                    )

                    if move:
                        move = move[0] if len(move) > 1 else move

                        # Handle bin location
                        bin_code = (line.get('SOFULFILLMENTBIN') or '').strip()
                        if bin_code:
                            move.write({'gp_bin_location': bin_code})

                        # Set qty_done on move lines
                        if move.move_line_ids:
                            for sml in move.move_line_ids:
                                sml.qty_done = qty_fulfilled
                        else:
                            # Create move line if none exists
                            self.env['stock.move.line'].create({
                                'move_id': move.id,
                                'picking_id': picking.id,
                                'product_id': move.product_id.id,
                                'product_uom_id': move.product_uom.id,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                                'qty_done': qty_fulfilled,
                                'company_id': move.company_id.id,
                            })

        # Validate the Pick operation if quantities are set
        # This will automatically create the Pack operation
        if picking.state == 'assigned':
            try:
                picking.button_validate()
                _logger.info(f'Validated Pick operation {picking.name} - Pack operation created automatically')
            except Exception as e:
                _logger.error(f'Error validating Pick operation {picking.name}: {str(e)}')
                # Try with immediate transfer wizard
                try:
                    wiz = self.env['stock.immediate.transfer'].create({
                        'pick_ids': [(4, picking.id)]
                    })
                    wiz.process()
                    _logger.info(f'Validated Pick operation {picking.name} with wizard')
                except Exception as e2:
                    _logger.error(f'Could not validate Pick operation {picking.name}: {str(e2)}')

    def _create_order_line(self, order, line_data):
        """Create order line from GP line data"""
        # Find or create product
        product = self.env['product.product'].find_or_create_from_gp(line_data)

        vals = {
            'order_id': order.id,
            'product_id': product.id,
            'name': line_data.get('ITEMDESC', product.name),
            'product_uom_qty': line_data.get('QUANTITY', 0),
            'price_unit': line_data.get('UNITPRCE', 0),
        }

        return self.env['sale.order.line'].create(vals)