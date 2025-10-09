# -*- coding: utf-8 -*-
{
    'name': 'Span Reports',
    'version': '18.0.1.0.0',
    'category': 'Warehouse',
    'summary': 'Custom reports for Span including container shipping labels',
    'description': """
        Span Reports Module
        ===================
        This module provides custom reports for Span operations including:
        - Container Shipping Labels
        - Additional reports to be added in future phases
    """,
    'author': 'IAS',
    'depends': [
        'stock',
        'delivery',
        'web',
        'delivery_nexterus',
        'gp_integration',
        'product_classification',
        'product_dimension',
    ],
    'data': [
        'security/ir.model.access.csv',
        'reports/report_actions.xml',
        'reports/shipping_label_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'span_reports/static/src/css/report_style.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}