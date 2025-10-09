from odoo import models, api, fields
from odoo.exceptions import UserError, ValidationError
import os
import logging
from datetime import datetime, timedelta
import re

_logger = logging.getLogger(__name__)


class EDIGenerator(models.Model):
    _name = 'edi.generator'
    _description = 'EDI 856 File Generator'

    @api.model
    def generate_856_files(self, config, pickings):
        """Generate EDI 856 files for given pickings"""
        if config.group_by_customer:
            # Group pickings by customer
            customer_pickings = {}
            for picking in pickings:
                partner = picking.partner_id
                if partner not in customer_pickings:
                    customer_pickings[partner] = self.env['stock.picking']
                customer_pickings[partner] |= picking

            # Generate one file per customer
            for partner, partner_pickings in customer_pickings.items():
                self._generate_customer_file(config, partner, partner_pickings)
        else:
            # Generate individual files
            for picking in pickings:
                self._generate_single_file(config, picking)

    def _generate_customer_file(self, config, partner, pickings):
        """Generate EDI file for a specific customer with multiple pickings"""
        try:
            # Get partner EDI config
            edi_partner_config = partner.edi_config_id
            if not edi_partner_config:
                if partner.edi_enabled:
                    # Create default configcron_generate_edi_856_files()
                    edi_partner_config = self.env['edi.partner.config'].create({
                        'partner_id': partner.id,
                        'edi_id': partner.edi_id or partner.ref or str(partner.id),
                        'edi_id_qualifier': partner.edi_id_qualifier or 'ZZ',
                    })
                else:
                    _logger.warning(f'Partner {partner.name} does not have EDI enabled')
                    return

            # Generate file name
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            random_suffix = str(datetime.now().microsecond).zfill(6)
            file_name = f"{config.file_prefix}{timestamp}{random_suffix}.{config.file_extension}"

            # Generate EDI content
            content = self._build_856_content(config, partner, pickings, edi_partner_config)

            # Write file
            file_path = os.path.join(config.output_path, file_name)
            with open(file_path, 'w') as f:
                f.write(content)

            # Archive if configured
            if config.archive_path and os.path.exists(config.archive_path):
                import shutil
                archive_file_path = os.path.join(config.archive_path, file_name)
                shutil.copy2(file_path, archive_file_path)

            # Mark pickings and create logs
            for picking in pickings:
                picking.write({
                    'edi_file_generated': True,
                    'edi_file_name': file_name,
                    'edi_generation_date': fields.Datetime.now(),
                })

                self.env['edi.log'].create({
                    'picking_id': picking.id,
                    'file_name': file_name,
                    'file_path': file_path,
                    'file_content': content[:5000],  # Store first 5000 chars
                    'status': 'success',
                    'control_number': self._get_control_number(),
                    'transaction_count': 1,
                })

            _logger.info(f'Generated EDI file: {file_name} for partner {partner.name}')

        except Exception as e:
            _logger.error(f'Error generating EDI file for partner {partner.name}: {str(e)}')
            # Create error log
            for picking in pickings:
                self.env['edi.log'].create({
                    'picking_id': picking.id,
                    'file_name': 'ERROR',
                    'status': 'error',
                    'error_message': str(e),
                })

    def _generate_single_file(self, config, picking):
        """Generate EDI file for a single picking"""
        self._generate_customer_file(config, picking.partner_id, picking)

    def _build_856_content(self, config, partner, pickings, edi_partner_config):
        """Build the EDI 856 content"""
        lines = []

        # Get control numbers
        control_number = self._get_control_number()
        group_number = self._get_group_number()

        # ISA - Interchange Control Header
        isa_line = self._build_isa_segment(config, partner, edi_partner_config, control_number)
        lines.append(isa_line)

        # GS - Functional Group Header
        gs_line = self._build_gs_segment(config, partner, edi_partner_config, group_number)
        lines.append(gs_line)

        # Process each picking as a transaction
        transaction_count = 0
        total_hl_count = 0

        for picking in pickings:
            transaction_count += 1
            transaction_id = f"{group_number}{transaction_count:02d}"

            # ST - Transaction Set Header
            lines.append(f"ST*856*{transaction_id}~")

            # BSN - Beginning Segment for Ship Notice
            bsn_line = self._build_bsn_segment(picking)
            lines.append(bsn_line)

            # Build hierarchical structure
            hl_segments, hl_count = self._build_hierarchical_structure(
                config, picking, edi_partner_config
            )
            lines.extend(hl_segments)
            total_hl_count += hl_count

            # CTT - Transaction Totals
            lines.append(f"CTT*{hl_count}~")

            # SE - Transaction Set Trailer
            segment_count = len([l for l in hl_segments if l]) + 3  # +3 for ST, BSN, CTT
            lines.append(f"SE*{segment_count}*{transaction_id}~")

        # GE - Functional Group Trailer
        lines.append(f"GE*{transaction_count}*{group_number}~")

        # IEA - Interchange Control Trailer
        lines.append(f"IEA*1*{control_number}~")

        return '\n'.join(lines)

    def _build_isa_segment(self, config, partner, edi_partner_config, control_number):
        """Build ISA segment"""
        now = datetime.now()
        date = now.strftime('%y%m%d')
        time = now.strftime('%H%M')

        # Receiver info
        receiver_id = edi_partner_config.edi_id or 'UNKNOWN'
        receiver_qualifier = edi_partner_config.edi_id_qualifier or 'ZZ'

        # Pad IDs to required length
        sender_id = config.sender_id.ljust(15)
        receiver_id = receiver_id.ljust(15)

        return (f"ISA*00*          *00*          *{config.sender_id_qualifier}*{sender_id}*"
                f"{receiver_qualifier}*{receiver_id}*{date}*{time}*U*00401*"
                f"{control_number}*0*P*:~")

    def _build_gs_segment(self, config, partner, edi_partner_config, group_number):
        """Build GS segment"""
        now = datetime.now()
        date = now.strftime('%Y%m%d')
        time = now.strftime('%H%M')

        receiver_id = edi_partner_config.edi_id or 'UNKNOWN'

        return (f"GS*SH*{config.sender_id}*{receiver_id}*{date}*{time}*"
                f"{group_number}*X*{config.edi_version}~")

    def _build_bsn_segment(self, picking):
        """Build BSN segment"""
        # Purpose code 00 = Original
        purpose = '00'

        # Shipment ID
        shipment_id = picking.name or datetime.now().strftime('%Y%m%d%H%M%S')

        # Date and time
        date = picking.date_done or datetime.now()
        ship_date = date.strftime('%Y%m%d')
        ship_time = date.strftime('%H%M%S')

        # Hierarchical structure code
        structure_code = '0002'  # Pick and Pack

        return f"BSN*{purpose}*{shipment_id}*{ship_date}*{ship_time}*{structure_code}~"

    def _build_hierarchical_structure(self, config, picking, edi_partner_config):
        """Build hierarchical loop structure for picking"""
        segments = []
        hl_counter = 0

        # HL*1 - Shipment Level
        hl_counter += 1
        shipment_hl = hl_counter
        segments.append(f"HL*{shipment_hl}**S~")

        # Calculate totals considering span packages
        total_weight = 0
        total_handling_units = 0

        # Get packages from move lines (from span_shipment module)
        packages = self.env['stock.quant.package']
        if picking.move_line_ids:
            for move_line in picking.move_line_ids:
                if move_line.result_package_id:
                    packages |= move_line.result_package_id

        if packages:
            for package in packages:
                total_weight += package.shipping_weight or 0
                total_handling_units += 1
        else:
            # Fallback to move quantities
            total_weight = sum(picking.move_ids.mapped(lambda m: m.product_qty * (m.product_id.weight or 0)))
            total_handling_units = 1

        # TD1 - Carrier Details with proper package type and count
        package_type = 'CTN25'  # Default carton
        if packages and packages[0].package_type_id:
            pkg_name = packages[0].package_type_id.name.upper()
            if 'PALLET' in pkg_name:
                package_type = 'PLT'
            elif 'SKID' in pkg_name:
                package_type = 'SKD'
            elif 'CRATE' in pkg_name:
                package_type = 'CRT'

        # Calculate total inner packages from span package info
        total_inner_packages = 0
        if packages:
            for package in packages:
                if hasattr(package, 'span_package_qty'):
                    total_inner_packages += package.span_package_qty or 1
                else:
                    total_inner_packages += 1
        else:
            total_inner_packages = 1

        segments.append(f"TD1*{package_type}*{total_handling_units}****G*{int(total_weight)}*LB~")

        # TD5 - Carrier Details (Routing)
        carrier_name = picking.carrier_id.name if picking.carrier_id else 'UNKNOWN'
        carrier_code = self._get_carrier_scac(picking)
        segments.append(f"TD5**2*{carrier_code}**{carrier_name}~")

        # REF - Reference Numbers
        if picking.carrier_tracking_ref:
            segments.append(f"REF*CN*{picking.carrier_tracking_ref}~")
        segments.append(f"REF*BM*{picking.name}~")

        # DTM - Date/Time
        ship_date = picking.date_done or datetime.now()
        segments.append(f"DTM*011*{ship_date.strftime('%Y%m%d')}~")

        # N1 - Name (Ship From)
        segments.append(f"N1*SF*{config.company_name}~")
        warehouse = picking.picking_type_id.warehouse_id
        if warehouse and warehouse.partner_id:
            addr = warehouse.partner_id
            segments.append(f"N3*{addr.street or ''}~")
            segments.append(f"N4*{addr.city or ''}*{addr.state_id.code if addr.state_id else ''}*{addr.zip or ''}~")

        # N1 - Name (Ship To)
        segments.append(f"N1*ST*{picking.partner_id.name}~")
        segments.append(f"N3*{picking.partner_id.street or ''}~")
        state_code = picking.partner_id.state_id.code if picking.partner_id.state_id else ''
        segments.append(f"N4*{picking.partner_id.city or ''}*{state_code}*{picking.partner_id.zip or ''}~")

        # HL*2 - Order Level
        hl_counter += 1
        order_hl = hl_counter
        segments.append(f"HL*{order_hl}*{shipment_hl}*O~")

        # PRF - Purchase Order Reference
        if picking.sale_id and picking.sale_id.gp_cstponbr:
            segments.append(f"PRF*{picking.sale_id.gp_cstponbr}~")
        elif picking.sale_id and picking.sale_id.gp_sopnumbe:
            segments.append(f"PRF*{picking.sale_id.gp_sopnumbe}~")
        elif picking.origin:
            segments.append(f"PRF*{picking.origin}~")

        # Check if we have move_line_ids
        if not picking.move_line_ids:
            # Use moves directly if no move lines exist
            for move in picking.move_ids:
                hl_counter += 1
                segments.append(f"HL*{hl_counter}*{order_hl}*I~")
                segments.extend(self._build_item_segments(move, edi_partner_config, picking.partner_id))
        else:
            # Process packages with proper hierarchy
            if packages and edi_partner_config.include_pack_level:
                # Tare/Package level - representing the main shipping container
                for package in packages:
                    hl_counter += 1
                    package_hl = hl_counter
                    segments.append(f"HL*{package_hl}*{order_hl}*T~")

                    # MAN - Marks and Numbers (Package tracking)
                    if hasattr(package, 'name'):
                        segments.append(f"MAN*GM*{package.name}~")

                    # Items in this package
                    package_move_lines = picking.move_line_ids.filtered(
                        lambda ml: ml.result_package_id == package
                    )

                    for move_line in package_move_lines:
                        hl_counter += 1
                        segments.append(f"HL*{hl_counter}*{package_hl}*I~")
                        segments.extend(self._build_item_segments_from_move_line(
                            move_line, edi_partner_config, picking.partner_id))
            else:
                # Direct item level (no packages) - use move lines
                for move_line in picking.move_line_ids:
                    hl_counter += 1
                    segments.append(f"HL*{hl_counter}*{order_hl}*I~")
                    segments.extend(self._build_item_segments_from_move_line(
                        move_line, edi_partner_config, picking.partner_id))

        return segments, hl_counter

    def _build_item_segments_from_move_line(self, move_line, edi_partner_config, partner):
        """Build item level segments from move line (has actual quantities)"""
        segments = []

        product = move_line.product_id

        # LIN - Item Identification
        item_code = product.default_code or product.name

        # Check for customer specific item code
        if edi_partner_config.use_customer_item_number:
            customer_code = self.env['product.customer.code'].search([
                ('partner_id', '=', partner.id),
                ('product_id', '=', product.id)
            ], limit=1)
            if customer_code:
                item_code = customer_code.customer_code

        # Check if product has vendor code
        if hasattr(product, 'seller_ids') and product.seller_ids:
            vendor_code = product.seller_ids[0].product_code if product.seller_ids else None
            if vendor_code:
                segments.append(f"LIN**VC*{vendor_code}*IN*{item_code}~")
            else:
                segments.append(f"LIN**IN*{item_code}~")
        else:
            segments.append(f"LIN**IN*{item_code}~")

        # SN1 - Item Detail (Shipment) - use qty_done from move line
        qty = int(move_line.qty_done)
        uom = self._get_uom_code(move_line.product_uom_id)
        segments.append(f"SN1**{qty}*{uom}~")

        # PID - Product/Item Description (optional)
        if product.name:
            desc = product.name[:80]
            desc = re.sub(r'[^\w\s-]', '', desc)
            segments.append(f"PID*F****{desc}~")

        # MAN - Serial/Lot numbers from move line
        if edi_partner_config.include_item_serial:
            if move_line.lot_id:
                segments.append(f"MAN*SM*{move_line.lot_id.name}~")

        return segments

    def _build_item_segments(self, move, edi_partner_config, partner):
        """Build item level segments from stock.move (fallback when no move_lines)"""
        segments = []

        product = move.product_id

        # LIN - Item Identification
        item_code = product.default_code or product.name

        # Check for customer specific item code
        if edi_partner_config.use_customer_item_number:
            customer_code = self.env['product.customer.code'].search([
                ('partner_id', '=', partner.id),
                ('product_id', '=', product.id)
            ], limit=1)
            if customer_code:
                item_code = customer_code.customer_code

        segments.append(f"LIN**IN*{item_code}~")

        # SN1 - Item Detail (Shipment)
        qty = int(move.product_qty)
        uom = self._get_uom_code(move.product_uom)
        segments.append(f"SN1**{qty}*{uom}~")

        # PID - Product/Item Description
        if product.name:
            desc = product.name[:80]
            desc = re.sub(r'[^\w\s-]', '', desc)
            segments.append(f"PID*F****{desc}~")

        return segments

    def _get_carrier_scac(self, picking):
        """Get carrier SCAC code"""
        if not picking.carrier_id:
            return 'UNKNOWN'

        # Check if carrier has SCAC in nexterus config
        if hasattr(picking.carrier_id, 'nexterus_scac') and picking.carrier_id.nexterus_scac:
            return picking.carrier_id.nexterus_scac

        # Common carrier mappings
        carrier_name = picking.carrier_id.name.upper()
        scac_mapping = {
            'FEDEX': 'FXFE',
            'FEDERAL EXPRESS': 'FXFE',
            'UPS': 'UPSG',
            'UNITED PARCEL': 'UPSG',
            'USPS': 'USPS',
            'DHL': 'DHLX',
            'TBB': 'TBB',
            'FAF': 'FAF',
        }

        for key, scac in scac_mapping.items():
            if key in carrier_name:
                return scac

        # Default to first 4 characters
        clean_name = re.sub(r'[^A-Z]', '', carrier_name)
        return clean_name[:4] if clean_name else 'UNKN'

    def _get_uom_code(self, uom):
        """Convert Odoo UOM to EDI UOM code"""
        uom_mapping = {
            'unit': 'EA',
            'units': 'EA',
            'each': 'EA',
            'dozen': 'DZ',
            'kg': 'KG',
            'lb': 'LB',
            'lbs': 'LB',
            'g': 'GR',
            'oz': 'OZ',
            'l': 'LT',
            'gal': 'GA',
            'case': 'CA',
            'cases': 'CA',
            'box': 'BX',
            'carton': 'CT',
            'pallet': 'PL',
            'pack': 'PK',
            'package': 'PK',
        }

        uom_name = uom.name.lower()
        for key, code in uom_mapping.items():
            if key in uom_name:
                return code

        return 'EA'  # Default to Each

    @api.model
    def _get_control_number(self):
        """Get next control number"""
        return self.env['ir.sequence'].next_by_code('edi.control.number')

    @api.model
    def _get_group_number(self):
        """Get next group number"""
        return self.env['ir.sequence'].next_by_code('edi.group.number')