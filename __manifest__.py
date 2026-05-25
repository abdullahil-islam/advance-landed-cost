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
        # Views — added per phase
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # OWL components added from Phase 7 onward
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
