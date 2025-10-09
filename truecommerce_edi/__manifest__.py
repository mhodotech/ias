{
    'name': 'TrueCommerce EDI 856 Integration',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Generate EDI 856 Advanced Ship Notice files for TrueCommerce',
    'description': """
        TrueCommerce EDI 856 Integration
        =================================

        This module generates EDI 856 (Advanced Ship Notice) files for validated deliveries.

        Features:
        - Automatic daily generation of EDI 856 files
        - Configurable shared folder path for file output
        - Customer-specific EDI configurations
        - Tracking of generated EDI files per delivery
        - Support for hierarchical loop structures
        - Batch processing by customer
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'stock',
        'delivery',
        'sale_stock',
        'product',
        'gp_integration',
        'span_shipment',
    ],
    'data': [
        'security/edi_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/ir_sequence_data.xml',
        'views/edi_config_views.xml',
        'views/res_partner_views.xml',
        'views/stock_picking_views.xml',
        'views/edi_log_views.xml',
        'wizard/edi_manual_generate_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'sequence' : '2',
    'auto_install': False,
    'license': 'LGPL-3',
}