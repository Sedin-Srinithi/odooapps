{
    'name': "ASP Connector-UAE eInvoicing",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations/EDI',
    'summary': 'Send Odoo invoices to ASP through a seamless integration',
    'description': """
        Multiple Asp E-Invoice Connector
        ===========================
        This module allows you to send UAE FTA compliant e-invoices 
        to Any ASP directly from Odoo.
        
        Features:
        - Auto-registration on install
        - HMAC secured requests  
        - UAE FTA PINT-AE compliant XML
        - One click invoice submission
        - Supports Invoice and Credit Note
        - Multi-currency support
    """,
    'author': 'Sedin Technologies ME LLC-FZ',
    # 'license': 'LGPL-3',
    'license': 'OPL-1',
    'depends': ['account'],
    'images': ['static/description/banner.gif'],
    'data': [
        'security/ir.model.access.csv',  
        'views/account_move_view.xml',
        # 'views/taxilla_setup_wizard.xml',    
        # 'views/taxilla_connection_views.xml',
        'views/res_company_view.xml', 
         'views/menu_view.xml',
    ],
    'post_init_hook': 'post_init_hook', 
    'installable': True,
    'application': True,

}
