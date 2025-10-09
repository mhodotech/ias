from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # EDI Configuration
    edi_enabled = fields.Boolean(
        'EDI Enabled',
        help='Enable EDI document generation for this partner'
    )
    edi_config_id = fields.One2many(
        'edi.partner.config',
        'partner_id',
        string='EDI Configuration'
    )

    # Quick EDI fields (most common)
    edi_id = fields.Char(
        related='edi_config_id.edi_id',
        string='EDI ID',
        readonly=False
    )
    edi_id_qualifier = fields.Selection(
        related='edi_config_id.edi_id_qualifier',
        string='EDI Qualifier',
        readonly=False
    )

    # Customer specific item numbers
    customer_item_ids = fields.One2many(
        'product.customer.code',
        'partner_id',
        string='Customer Item Numbers'
    )

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if partner.edi_enabled and not partner.edi_config_id:
                # Auto-create EDI config
                self.env['edi.partner.config'].create({
                    'partner_id': partner.id,
                    'edi_id': partner.ref or partner.id,
                    'edi_id_qualifier': 'ZZ',
                })
        return partners


class ProductCustomerCode(models.Model):
    _name = 'product.customer.code'
    _description = 'Product Customer Code'
    _rec_name = 'customer_code'

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='cascade'
    )
    customer_code = fields.Char(
        'Customer Item Code',
        required=True,
        help='Item code used by customer'
    )
    active = fields.Boolean('Active', default=True)

    _sql_constraints = [
        ('partner_product_uniq', 'UNIQUE(partner_id, product_id)',
         'Customer code already exists for this product and partner!'),
    ]