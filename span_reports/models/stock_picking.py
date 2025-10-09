# -*- coding: utf-8 -*-

from odoo import models, fields, api
import base64
import io
from reportlab.graphics import barcode
from reportlab.lib.units import mm


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def get_container_report_data(self):
        """Prepare data for container shipping label report"""
        self.ensure_one()

        # Get shipping address
        ship_to_address = []
        if self.partner_id:
            ship_to_address.append(self.partner_id.name or '')
            if self.partner_id.street:
                ship_to_address.append(self.partner_id.street)
            if self.partner_id.street2:
                ship_to_address.append(self.partner_id.street2)
            city_state_zip = []
            if self.partner_id.city:
                city_state_zip.append(self.partner_id.city)
            if self.partner_id.state_id:
                city_state_zip.append(self.partner_id.state_id.code)
            if self.partner_id.zip:
                city_state_zip.append(self.partner_id.zip)
            if city_state_zip:
                ship_to_address.append(', '.join(city_state_zip))
            if self.partner_id.country_id:
                ship_to_address.append(self.partner_id.country_id.name)

        # Get carrier info - check if carrier exists
        carrier_name = 'TBD'
        if self.carrier_id and self.carrier_id.name:
            carrier_name = self.carrier_id.name

        # Get PRO number - assuming it's stored in a field from nexterus module
        pro_number = ''
        if hasattr(self, 'nexterus_pro_number'):
            pro_number = self.nexterus_pro_number or ''
        elif hasattr(self, 'pro_number'):
            pro_number = self.pro_number or ''

        # Get GP fields if they exist
        gp_order = ''
        gp_po = ''
        if hasattr(self, 'gp_sopnumbe'):
            gp_order = self.gp_sopnumbe or ''
        if hasattr(self, 'gp_cstponbr'):
            gp_po = self.gp_cstponbr or ''

        # Container count - you can adjust this logic
        container_count = 1
        total_containers = 1

        # Get items data
        items_data = []
        for move_line in self.move_line_ids_without_package:
            item_data = {
                'qty': int(move_line.quantity),
                'item_code': move_line.product_id.default_code or '',
                'description': move_line.product_id.name or '',
            }
            items_data.append(item_data)

        # If no move lines, check move_ids
        if not items_data:
            for move in self.move_ids:
                item_data = {
                    'qty': int(move.product_uom_qty),
                    'item_code': move.product_id.default_code or '',
                    'description': move.product_id.name or '',
                }
                items_data.append(item_data)

        return {
            'shipment_number': self.name or '',
            'order_number': gp_order,
            'date': self.scheduled_date or self.date_deadline or fields.Date.today(),
            'po_number': gp_po,
            'ship_to': ship_to_address,
            'carrier': carrier_name,
            'pro_number': pro_number,
            'pro_barcode': self._generate_barcode_base64(pro_number) if pro_number else False,
            'container_number': container_count,
            'total_containers': total_containers,
            'items': items_data,
        }

    def _generate_barcode_base64(self, value):
        """Generate Code39 barcode and return as base64 string"""
        if not value:
            return False

        try:
            # Create barcode
            barcode_obj = barcode.createBarcodeDrawing(
                'Code39',
                value=str(value),
                barHeight=10 * mm,
                width=2,
                humanReadable=False
            )

            # Convert to image
            buffer = io.BytesIO()
            barcode_obj.save(formats=['PNG'], fnRoot=buffer)
            img_str = base64.b64encode(buffer.getvalue())
            return img_str.decode('utf-8')
        except Exception:
            return False