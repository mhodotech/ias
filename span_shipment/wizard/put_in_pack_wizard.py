# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PutInPackWizard(models.TransientModel):
    _name = 'put.in.pack.wizard'
    _description = 'Put in Pack Wizard'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Picking'
    )
    batch_id = fields.Many2one(
        'stock.picking.batch',
        string='Batch'
    )
    move_line_ids = fields.Many2many(
        'stock.move.line',
        string='Products to Pack'
    )

    # Package type
    package_type_id = fields.Many2one(
        'stock.package.type',
        string='Package Type',
        required=True
    )

    # Dimensions and weight
    shipping_weight = fields.Float(
        string='Shipping Weight (lbs)',
        compute='_compute_shipping_weight',
        store=True,
        readonly=False,
        default = 1.0
    )
    shipping_length = fields.Float(
        string='Length (in)',
        compute='_compute_dimensions',
        store=True,
        readonly=False,
        default=48
    )
    shipping_width = fields.Float(
        string='Width (in)',
        compute='_compute_dimensions',
        store=True,
        readonly=False,
        default=40
    )
    shipping_height = fields.Float(
        string='Height (in)',
        compute='_compute_dimensions',
        store=True,
        readonly=False,
        default=48
    )

    # PCF calculation
    pcf = fields.Float(
        string='PCF',
        compute='_compute_pcf',
        help='Pounds per Cubic Foot'
    )
    suggested_class = fields.Selection([
        ('50', 'Class 50'),
        ('55', 'Class 55'),
        ('60', 'Class 60'),
        ('65', 'Class 65'),
        ('70', 'Class 70'),
        ('77.5', 'Class 77.5'),
        ('85', 'Class 85'),
        ('92.5', 'Class 92.5'),
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
    ], string='Suggested Class', compute='_compute_suggested_class')

    # NMFC fields
    nmfc_code = fields.Char(
        string='NMFC Code',
        compute='_compute_nmfc_info',
        store=True,
        readonly=False
    )

    nmfc_class = fields.Selection([
        ('50', 'Class 50'),
        ('55', 'Class 55'),
        ('60', 'Class 60'),
        ('65', 'Class 65'),
        ('70', 'Class 70'),
        ('77.5', 'Class 77.5'),
        ('85', 'Class 85'),
        ('92.5', 'Class 92.5'),
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
    ], string='Freight Class', required=True, default='85')

    # Commodity
    commodity_description_id = fields.Many2one(
        'commodity.description',
        string='Commodity Description',
        required=True
    )

    # Span package
    span_package_type_id = fields.Many2one(
        'span.package.type',
        string='Span Package Type'
    )
    span_package_qty = fields.Integer(
        string='Span Quantity',
        default=1
    )

    # Special handling
    is_hazmat = fields.Boolean(
        string='Hazardous Material',
        compute='_compute_hazmat',
        store=True,
        readonly=False
    )
    special_handling = fields.Text(
        string='Special Handling Instructions'
    )

    @api.depends('move_line_ids', 'package_type_id')
    def _compute_shipping_weight(self):
        for wizard in self:
            product_weight = sum(wizard.move_line_ids.mapped(
                lambda ml: ml.qty_done * ml.product_id.weight  # Changed from quantity to qty_done
            ))
            package_weight = wizard.package_type_id.max_weight if wizard.package_type_id else 0
            wizard.shipping_weight = product_weight + package_weight

    @api.depends('package_type_id')
    def _compute_dimensions(self):
        for wizard in self:
            if wizard.package_type_id:
                wizard.shipping_length = wizard.package_type_id.packaging_length or 48
                wizard.shipping_width = wizard.package_type_id.width or 40
                wizard.shipping_height = wizard.package_type_id.height or 48

    @api.depends('shipping_length', 'shipping_width', 'shipping_height', 'shipping_weight')
    def _compute_pcf(self):
        for wizard in self:
            if all([wizard.shipping_length, wizard.shipping_width,
                    wizard.shipping_height, wizard.shipping_weight]):
                cubic_inches = wizard.shipping_length * wizard.shipping_width * wizard.shipping_height
                cubic_feet = cubic_inches / 1728.0
                if cubic_feet > 0:
                    wizard.pcf = wizard.shipping_weight / cubic_feet
                else:
                    wizard.pcf = 0.0
            else:
                wizard.pcf = 0.0

    @api.depends('pcf')
    def _compute_suggested_class(self):
        """
        Freight class based on PCF (density)
        Higher density = Lower class number = Lower cost
        """
        for wizard in self:
            pcf = wizard.pcf
            if pcf >= 50:
                wizard.suggested_class = '50'
            elif pcf >= 35:
                wizard.suggested_class = '55'
            elif pcf >= 30:
                wizard.suggested_class = '60'
            elif pcf >= 22.5:
                wizard.suggested_class = '65'
            elif pcf >= 15:
                wizard.suggested_class = '70'
            elif pcf >= 13.5:
                wizard.suggested_class = '77.5'
            elif pcf >= 12:
                wizard.suggested_class = '85'
            elif pcf >= 10.5:
                wizard.suggested_class = '92.5'
            elif pcf >= 9:
                wizard.suggested_class = '100'
            elif pcf >= 8:
                wizard.suggested_class = '110'
            elif pcf >= 7:
                wizard.suggested_class = '125'
            elif pcf >= 6:
                wizard.suggested_class = '150'
            elif pcf >= 5:
                wizard.suggested_class = '175'
            elif pcf >= 4:
                wizard.suggested_class = '200'
            elif pcf >= 3:
                wizard.suggested_class = '250'
            elif pcf >= 2:
                wizard.suggested_class = '300'
            elif pcf >= 1:
                wizard.suggested_class = '400'
            else:
                wizard.suggested_class = '500'

    @api.depends('move_line_ids')
    def _compute_nmfc_info(self):
        for wizard in self:
            products = wizard.move_line_ids.mapped('product_id')

            # If all products have same NMFC info, use it
            nmfc_codes = products.mapped('nmfc_code')
            nmfc_codes = [c for c in nmfc_codes if c]
            if nmfc_codes and len(set(nmfc_codes)) == 1:
                wizard.nmfc_code = nmfc_codes[0]

            nmfc_classes = products.mapped('nmfc_class')
            nmfc_classes = [c for c in nmfc_classes if c]
            if nmfc_classes and len(set(nmfc_classes)) == 1:
                wizard.nmfc_class = nmfc_classes[0]

            if not wizard.commodity_description_id:
                nmfc_descs = products.mapped('nmfc_description_id')
                nmfc_descs = [d for d in nmfc_descs if d]
                if nmfc_descs and len(set(nmfc_descs)) == 1:
                    wizard.commodity_description_id = nmfc_descs[0]

    @api.depends('move_line_ids')
    def _compute_hazmat(self):
        for wizard in self:
            wizard.is_hazmat = any(wizard.move_line_ids.mapped('product_id.is_hazmat'))

    @api.onchange('package_type_id')
    def _onchange_package_type_id(self):
        """Set default values when package type changes"""
        if self.package_type_id:
            # Try to get default commodity from package type name
            commodity = self.env['commodity.description'].search([
                ('name', 'ilike', self.package_type_id.name)
            ], limit=1)
            if commodity:
                self.commodity_description_id = commodity

    def action_create_package(self):
        """Create package and assign to move lines"""
        self.ensure_one()

        if self.picking_id:
            location_id = self.picking_id.location_dest_id.id
        elif self.batch_id and self.move_line_ids:
            location_id = self.move_line_ids[0].location_dest_id.id
        else:
            raise UserError(_('Cannot determine package location'))

        # Create the quant package with all shipping data
        package_vals = {
            'name': self.env['ir.sequence'].next_by_code('stock.quant.package') or _('PACK'),
            'package_type_id': self.package_type_id.id,
            'shipping_weight': self.shipping_weight,
            'shipping_length': self.shipping_length,
            'shipping_width': self.shipping_width,
            'shipping_height': self.shipping_height,
            'nmfc_code': self.nmfc_code,
            'nmfc_class': self.nmfc_class,
            'commodity_description_id': self.commodity_description_id.id,
            'span_package_type_id': self.span_package_type_id.id if self.span_package_type_id else False,
            'span_package_qty': self.span_package_qty,
            'is_hazmat': self.is_hazmat,
            'special_handling': self.special_handling,
        }

        package = self.env['stock.quant.package'].create(package_vals)


        # Link package to move lines
        self.move_line_ids.write({
            'result_package_id': package.id,
            'picked': False,  # Reset picked flag after packing
        })

        # Success message and close wizard
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Package %s created successfully') % package.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }