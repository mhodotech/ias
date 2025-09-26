# -*- coding: utf-8 -*-
{
    "name": "Product Classification",
    "version": "18.0.1.0.0",
    "category": "Product",
    "summary": "Add NMFC, Class, and Commodity Description to products",
    "description": """
        This module adds classification fields to products:
        - NMFC (National Motor Freight Classification)
        - Class
        - Commodity Description
        
        These fields are added in the Inventory tab under a Classification section.
    """,
    "author": "IAS",
    "license": "AGPL-3",
    "website": "https://www.infoagesolutions.com",
    "depends": ["product"],
    "data": [
        "views/product_classification_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
