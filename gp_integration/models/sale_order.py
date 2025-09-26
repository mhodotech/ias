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
        """Create or update sale order from GP data"""
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

        # Auto-confirm if has picking ticket
        if gp_data.get('PCKSLPNO'):
            order.action_confirm()

            # Process picking if needed
            if gp_data.get('has_fulfillment'):
                order.process_gp_picking(gp_data, line_data)

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

        # Process picking if needed and not already done
        if gp_data.get('PCKSLPNO') and order.state == 'draft':
            order.action_confirm()

        # Update packing transfer name if it exists
        gp_pckslpno = gp_data.get('PCKSLPNO', '').strip()
        if gp_pckslpno:
            # Find any packing transfers that don't have the right name
            packing = order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == 'internal' and
                          'Pack' in (p.picking_type_id.name or '') and
                          p.name != gp_pckslpno
            )

            if packing:
                packing = packing[0] if len(packing) > 1 else packing
                packing.write({
                    'name': gp_pckslpno,
                    'gp_pckslpno': gp_pckslpno,
                    'gp_bachnumb': gp_data.get('BACHNUMB', ''),
                })
                _logger.info(f'Updated packing transfer name to {gp_pckslpno}')

        # Check if pickings exist, create if missing
        if order.state in ['sale', 'done']:
            picking = order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == 'internal' and
                          'Pick' in (p.picking_type_id.name or '')
            )

            if not picking:
                # Pickings were deleted, recreate them
                _logger.warning(f'Pickings missing for order {order.name}, recreating...')
                order.action_confirm()
                # Force recreation of deliveries
                order._create_delivery()

                picking = order.picking_ids.filtered(
                    lambda p: p.picking_type_id.code == 'internal' and
                              'Pick' in (p.picking_type_id.name or '')
                )

            # Process fulfillment if GP has fulfillment
            if gp_data.get('has_fulfillment'):
                picking = order.picking_ids.filtered(
                    lambda p: p.picking_type_id.code == 'internal' and
                              'Pick' in (p.picking_type_id.name or '')
                )

                if picking:
                    # Check if picking is not already done
                    picking_to_process = picking.filtered(lambda p: p.state != 'done')

                    if picking_to_process:
                        # Process the picking (validate it)
                        for pick in picking_to_process:
                            self._process_single_picking(pick, gp_data, line_data)

                    # After picking is done, handle packing transfer
                    self._update_packing_transfer(order, gp_data)

        return order

    def _process_single_picking(self, picking, gp_data, line_data):
        """Process a single picking - extracted for reuse"""
        # Update picking with GP data
        picking.write({
            'gp_pckslpno': gp_data.get('PCKSLPNO', ''),
            'gp_bachnumb': gp_data.get('BACHNUMB', ''),
            'scheduled_date': gp_data.get('FUFILDAT') or fields.Datetime.now(),
        })

        # Ensure reservations exist
        if picking.state in ['confirmed', 'waiting']:
            picking.action_assign()

        # Process move lines based on GP fulfilled quantities
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

        # Validate the picking
        if picking.state in ['assigned', 'confirmed', 'waiting']:
            try:
                if picking.state != 'assigned':
                    picking.action_assign()

                picking.button_validate()
                _logger.info(f'Validated picking {picking.name}')

            except Exception as e:
                _logger.error('Error validating picking %s: %s', picking.name, e)
                try:
                    if 'stock.immediate.transfer' in self.env:
                        wiz = self.env['stock.immediate.transfer'].create({
                            'pick_ids': [(4, picking.id)]
                        })
                        wiz.process()
                except:
                    _logger.error(f'Could not validate picking {picking.name}')

    def _update_packing_transfer(self, order, gp_data):
        """Update or create packing transfer with GP name"""
        gp_pckslpno = gp_data.get('PCKSLPNO', '').strip()

        if gp_pckslpno:
            # Find packing transfer
            packing = order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == 'internal' and
                          'Pack' in (p.picking_type_id.name or '')
            )

            if packing:
                packing = packing[0] if len(packing) > 1 else packing
                packing.write({
                    'name': gp_pckslpno,
                    'gp_pckslpno': gp_pckslpno,
                    'gp_bachnumb': gp_data.get('BACHNUMB', ''),
                })
                _logger.info(f'Updated packing transfer name to {gp_pckslpno}')

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

    # Updated process_gp_picking method for sale_order.py
    # This replaces the existing process_gp_picking method in the SaleOrder class

    def process_gp_picking(self, gp_data, line_data):
        """Process picking order from GP data - Odoo 18 compatible"""
        self.ensure_one()

        # Get the picking order (first step in 3-step delivery)
        picking = self.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'internal' and
                      p.location_dest_id.usage == 'internal' and
                      'Pick' in (p.picking_type_id.name or '')
        )

        if not picking:
            _logger.warning(f'No picking order found for {self.name}')
            return

        picking = picking[0] if len(picking) > 1 else picking

        # Use the extracted method
        self._process_single_picking(picking, gp_data, line_data)

        # Handle packing transfer naming
        self._update_packing_transfer(self, gp_data)

        _logger.info(f'Processed GP picking for order {self.name}')