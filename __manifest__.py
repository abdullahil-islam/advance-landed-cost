{
    'name': 'Advance Landed Cost',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Advanced customs duties and landed cost management for import-heavy businesses',
    'description': """
        Extends Odoo's standard landed cost with:
        - HS Code management with product/category inheritance
        - Customs duty rate table with country/region lookup priority
        - CIF calculation engine with 5 split methods
        - Per-levy breakdown: Duty, VAT, CESS, SSCL
        - One-click bill generation (customs, shipping, insurance)
        - Custom journal entries for duty accounting
        - Approval workflow: Draft → Confirmed → Approved → Done
        - Full audit trails for CIF and duty manual overrides
        - Multi-company support with global/company-specific rates
    """,
    'author': 'Advance Landed Cost',
    'license': 'OPL-1',
    'depends': [
        'stock_landed_costs',
        'stock_account',
        'account',
        'purchase',
        'product',
    ],
    'data': [
        # Security — must load first
        'security/advance_landed_cost_groups.xml',
        'security/ir.model.access.csv',
        'security/advance_landed_cost_security.xml',
        # Data
        'data/ir_sequence_data.xml',
        'data/customs_demo_data.xml',
        # Views — Phase 2: HS Code Management
        'views/customs_hs_code_views.xml',
        'views/product_category_views.xml',
        'views/product_template_views.xml',
        # Views — Phase 3: Rate Configuration
        'views/customs_duty_region_views.xml',
        'views/customs_duty_levy_views.xml',
        'views/customs_duty_rate_views.xml',
        'views/res_config_settings_views.xml',
        # Views — Phase 4: Landed Cost Extension
        'views/stock_landed_cost_views.xml',
        'views/account_move_views.xml',
        # Wizards — Phase 5: CIF Engine
        'wizard/customs_recalculate_wizard_views.xml',
        # Wizards — Phase 6: Duty Override
        'wizard/customs_duty_override_wizard_views.xml',
        # Menus — after all actions are defined
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advance_landed_cost/static/src/components/bill_summary_widget/bill_summary_widget.js',
            'advance_landed_cost/static/src/components/bill_summary_widget/bill_summary_widget.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
