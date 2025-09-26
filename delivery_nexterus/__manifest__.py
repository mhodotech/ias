# -*- coding: utf-8 -*-
{
    'name': "Nexterus Shipping Integration",
    'summary': """
        LTL Freight shipping integration with Nexterus TMS.
        Get real-time freight rates, create shipments, and track deliveries.
    """,
    'description': """
        Nexterus Transport Management System Integration
        ================================================

        This module integrates Nexterus' LTL freight services directly into Odoo 18,
        providing comprehensive shipping management capabilities including:

        Features:
        ---------
        * Real-time LTL freight rate shopping from multiple carriers
        * Dynamic carrier creation from Nexterus rates
        * Automatic shipment creation and booking
        * PRO number generation
        * Bill of Lading generation
        * Shipping label printing
        * Real-time tracking
        * Support for accessorials (liftgate, inside delivery, etc.)
        * NMFC and freight class management
        * Package management using Odoo's native package types
        * Bulk carrier closing with email notifications

        Key Improvements in v18:
        ------------------------
        * Each Nexterus carrier is now a separate shipping method
        * Dynamic carrier creation when selecting from rates
        * Simplified interface without redundant tabs
        * Native package management integration
        * Bulk operations for closing carriers
        * Email notification system for carrier operations

        Supported Carriers:
        -------------------
        * Daylight Transport
        * TForce Freight
        * Southeastern Freight Lines
        * Saia Motor Freight
        * Estes Express Lines
        * Old Dominion Freight Line
        * FedEx Freight
        * And many more through Nexterus network
    """,
    'category': 'Inventory/Delivery',
    'version': '18.0.2.0.0',
    'license': 'LGPL-3',
    'author': 'IAS',
    'website': 'https://www.infoagesolutions.com',
    'depends': [
        'sale',
        'stock',
        'delivery',
        'stock_delivery',
        'product',
        'product_classification',  # For NMFC and freight class fields
        'mail',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',

        # Data files
        'data/delivery_nexterus_data.xml',
        'data/email_template.xml',

        # Views - Order matters!
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'views/carrier_close_config_views.xml',
        'views/carrier_close_views.xml',

        # Wizard views
        'wizard/choose_delivery_carrier_views.xml',
        'wizard/carrier_rates_views.xml',
        'wizard/close_carrier_wizard_views.xml',
    ],
    'demo': [],
    'qweb': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': None,
    'uninstall_hook': None,
    'external_dependencies': {
        'python': ['requests'],
    },
    'assets': {},
}