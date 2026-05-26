from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ── Levy toggles ──────────────────────────────────────────────────────────
    customs_enable_vat = fields.Boolean(
        'Enable VAT Calculation', default=True)
    customs_enable_cess = fields.Boolean(
        'Enable CESS Calculation', default=True)
    customs_enable_sscl = fields.Boolean(
        'Enable SSCL Calculation', default=False)
    customs_cif_uplift = fields.Boolean(
        'Apply 10% CIF Uplift for Tax Base',
        default=False,
        help='Multiply CIF × 1.10 when computing the base for VAT, CESS, and SSCL. '
             'Customs duty is always computed on the original CIF.',
    )
    customs_allow_manual_override = fields.Boolean(
        'Allow Manual Duty Override',
        default=True,
        help='Allow Customs Managers to manually override computed duty amounts.',
    )

    # ── Journal for customs duty entries ─────────────────────────────────────
    customs_journal_id = fields.Many2one(
        'account.journal',
        string='Customs Journal',
        domain=[('type', '=', 'general')],
        help='Journal used for customs duty journal entries posted at validation. '
             'Falls back to any general journal if not set.',
    )

    # ── Accounting accounts (used in Phase 8 journal entries) ─────────────────
    customs_duty_payable_account_id = fields.Many2one(
        'account.account',
        string='Customs Duty Payable Account',
        domain=[('deprecated', '=', False)],
    )
    customs_vat_receivable_account_id = fields.Many2one(
        'account.account',
        string='VAT Receivable Account',
        domain=[('deprecated', '=', False)],
    )
    customs_vat_payable_account_id = fields.Many2one(
        'account.account',
        string='VAT Payable Account',
        domain=[('deprecated', '=', False)],
    )
    customs_freight_payable_account_id = fields.Many2one(
        'account.account',
        string='Freight Payable Account',
        domain=[('deprecated', '=', False)],
    )
    customs_insurance_payable_account_id = fields.Many2one(
        'account.account',
        string='Insurance Payable Account',
        domain=[('deprecated', '=', False)],
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Journal
    customs_journal_id = fields.Many2one(
        related='company_id.customs_journal_id',
        readonly=False,
        string='Customs Journal',
    )

    # Levy toggles — stored on res.company, scoped per company
    customs_enable_vat = fields.Boolean(
        related='company_id.customs_enable_vat',
        readonly=False,
        string='Enable VAT',
    )
    customs_enable_cess = fields.Boolean(
        related='company_id.customs_enable_cess',
        readonly=False,
        string='Enable CESS',
    )
    customs_enable_sscl = fields.Boolean(
        related='company_id.customs_enable_sscl',
        readonly=False,
        string='Enable SSCL',
    )
    customs_cif_uplift = fields.Boolean(
        related='company_id.customs_cif_uplift',
        readonly=False,
        string='Apply 10% CIF Uplift',
    )
    customs_allow_manual_override = fields.Boolean(
        related='company_id.customs_allow_manual_override',
        readonly=False,
        string='Allow Manual Duty Override',
    )

    # Accounting accounts
    customs_duty_payable_account_id = fields.Many2one(
        related='company_id.customs_duty_payable_account_id',
        readonly=False,
        string='Customs Duty Payable',
    )
    customs_vat_receivable_account_id = fields.Many2one(
        related='company_id.customs_vat_receivable_account_id',
        readonly=False,
        string='VAT Receivable',
    )
    customs_vat_payable_account_id = fields.Many2one(
        related='company_id.customs_vat_payable_account_id',
        readonly=False,
        string='VAT Payable',
    )
    customs_freight_payable_account_id = fields.Many2one(
        related='company_id.customs_freight_payable_account_id',
        readonly=False,
        string='Freight Payable',
    )
    customs_insurance_payable_account_id = fields.Many2one(
        related='company_id.customs_insurance_payable_account_id',
        readonly=False,
        string='Insurance Payable',
    )
