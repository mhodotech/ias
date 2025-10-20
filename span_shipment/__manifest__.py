# -*- coding: utf-8 -*-
{
    'name': "Span Shipment",
    'summary': """
        Comprehensive shipping management for LTL and Parcel shipments.
        Integrates with Nexterus for LTL freight and standard carriers for parcel.
    """,
    'description': """
        Span Shipment Management System
        ================================

        This module provides complete shipping management including:

        Features:
        ---------
        * Product dimension and PCF management
        * Advanced package creation with NMFC codes
        * Real-time LTL freight rates via Nexterus
        * Parcel shipping via FedEx/UPS/USPS
        * Batch picking with package management
        * Special services (liftgate, inside delivery)
        * Carrier rate management and expiration
        * Bulk carrier closing with notifications

        Workflow:
        ---------
        1. Mark products as picked
        2. Put in pack with detailed package info
        3. Get rates from carriers
        4. Create shipment and receive tracking
        5. Validate picking manually
    """,
    'category': 'Inventory/Delivery',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'author': 'Span America',
    'website': 'https://www.spanamerica.com',
    'depends': [
        'sale',
        'stock',
        'delivery',
        'stock_delivery',
        'product',
        'mail',
        'stock_picking_batch',
        'gp_integration',  # Add this if not already there
        'truecommerce_edi',
    ],

    'assets': {
            'web.report_assets_common': [
                'span_shipment/static/src/css/container_label.css',
            ],
            'web.assets_backend': [
                        'span_shipment/static/src/css/span_shipment_opening_screen.css',
                        'span_shipment/static/src/js/span_shipment_opening_screen.js',
                        'span_shipment/static/src/xml/span_shipment_opening_screen.xml',
                    ],
        },

    'data': [
        # Security
        'security/ir.model.access.csv',

        # Data files
        'data/span_shipment_data.xml',
        'data/email_template.xml',
        'data/paperformat.xml',

        # Reports
        'reports/container_label_report.xml',
        'reports/container_label_templates.xml',
        'reports/bill_of_lading_report.xml',
        'reports/bill_of_lading_templates.xml',

        # Views - Order matters!
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/stock_quant_package_views.xml',
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_move_line_views.xml',
        'views/stock_picking_batch_views.xml',
        'views/shipment_rate_views.xml',
        'views/carrier_close_config_views.xml',
        'views/span_package_type_views.xml',
        'views/commodity_description_views.xml',
        'views/span_shipment_opening_screen_menu.xml',

        # Wizard views
        'wizard/put_in_pack_wizard_views.xml',
        'wizard/get_rates_wizard_views.xml',
        'wizard/close_carrier_wizard_views.xml',

        # Menus
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'sequence': '1',
    'auto_install': False,
    'external_dependencies': {
        'python': ['requests'],
    },
}