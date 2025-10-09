from odoo import models, fields, api
from odoo.exceptions import ValidationError
import os
import logging

_logger = logging.getLogger(__name__)


class EDIConfig(models.Model):
    _name = 'edi.config'
    _description = 'EDI Configuration'
    _rec_name = 'name'

    name = fields.Char('Configuration Name', required=True, default='TrueCommerce EDI')
    active = fields.Boolean('Active', default=True)

    # File Path Configuration
    output_path = fields.Char(
        'Output Folder Path',
        required=True,
        help='Shared folder path where EDI files will be generated'
    )
    archive_path = fields.Char(
        'Archive Folder Path',
        help='Optional path to archive generated EDI files'
    )

    # Sender/Receiver Information
    sender_id = fields.Char(
        'Sender ID',
        required=True,
        default='8008886752',
        help='ISA06 - Interchange Sender ID'
    )
    sender_id_qualifier = fields.Selection([
        ('01', 'Duns'),
        ('12', 'Phone'),
        ('14', 'Duns Plus Suffix'),
        ('ZZ', 'Mutually Defined'),
    ], string='Sender ID Qualifier', default='12', required=True, help='ISA05')

    receiver_id_qualifier = fields.Selection([
        ('01', 'Duns'),
        ('12', 'Phone'),
        ('14', 'Duns Plus Suffix'),
        ('ZZ', 'Mutually Defined'),
    ], string='Receiver ID Qualifier', default='ZZ', help='ISA07')

    # EDI Standards
    edi_version = fields.Char(
        'EDI Version',
        default='004010',
        required=True,
        help='Version of X12 standard'
    )

    # File naming
    file_prefix = fields.Char(
        'File Prefix',
        default='856',
        help='Prefix for generated file names'
    )
    file_extension = fields.Char(
        'File Extension',
        default='tdf',
        required=True,
        help='File extension (tdf, edi, txt, etc.)'
    )

    # Processing Options
    group_by_customer = fields.Boolean(
        'Group by Customer',
        default=True,
        help='Generate one file per customer per day'
    )
    include_serial_numbers = fields.Boolean(
        'Include Serial Numbers',
        default=True,
        help='Include serial numbers in MAN segments when available'
    )

    # Company defaults
    company_name = fields.Char(
        'Company Name',
        default='SPAN-AMERICA MEDICAL SYSTEMS',
        required=True
    )
    company_code = fields.Char(
        'Company Code',
        help='Company identifier code if required'
    )

    @api.constrains('active')
    def _check_single_active(self):
        if self.active and self.search_count([('active', '=', True)]) > 1:
            raise ValidationError('Only one EDI configuration can be active at a time')

    @api.constrains('output_path', 'archive_path')
    def _check_paths(self):
        for record in self:
            if record.output_path and not os.path.exists(record.output_path):
                raise ValidationError(f'Output path does not exist: {record.output_path}')
            if record.archive_path and not os.path.exists(record.archive_path):
                raise ValidationError(f'Archive path does not exist: {record.archive_path}')

    @api.model
    def cron_generate_edi_856_files(self):
        """Cron method to generate EDI 856 files daily"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            _logger.warning('No active EDI configuration found')
            return

        # Get yesterday's validated deliveries
        from datetime import datetime, timedelta
        yesterday = datetime.now() - timedelta(days=1)
        start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

        deliveries = self.env['stock.picking'].search([
            ('picking_type_id.code', '=', 'outgoing'),
            ('state', '=', 'done'),
            ('edi_file_generated', '=', False)
        ])

        if not deliveries:
            _logger.info('No deliveries found for EDI generation')
            return

        # Generate EDI files
        generator = self.env['edi.generator']
        generator.generate_856_files(config, deliveries)

        _logger.info(f'Generated EDI files for {len(deliveries)} deliveries')
