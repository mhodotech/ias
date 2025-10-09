{
    'name': 'GP Sales Order Integration',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Sync sales orders from Microsoft Dynamics GP to Odoo',
    'description': """
        GP Sales Order Integration Module
        ==================================

        This module synchronizes sales orders from Microsoft Dynamics GP 2018 R2 to Odoo 18.

        Features:
        - Sync active sales orders from GP (SOP10100/SOP10200)
        - Create/update products on the fly
        - Handle 3-step delivery process (Pick, Pack, Ship)
        - Process picking orders from GP
        - Track GP IDs in Odoo
        - Queue job processing for better performance

        Requires:
        - pyodbc (installed in Docker container)
        - FreeTDS driver
        - queue_job OCA module
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'sale_management',
        'stock',
        'product',
        'queue_job',
    ],
    'data': [
        'security/gp_integration_security.xml',
        'security/ir.model.access.csv',
        'data/queue_job_channel_data.xml',
        'data/queue_job_function_data.xml',
        'data/ir_cron_data.xml',
        'views/gp_config_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'views/product_views.xml',
        'views/res_partner_views.xml',
        'views/gp_sync_log_views.xml',
        'views/gp_shipment_notification_views.xml',
        'wizards/gp_sync_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'sequence' : '3',
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['pyodbc'],
    },
}