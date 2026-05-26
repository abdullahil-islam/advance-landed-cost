from odoo import api, fields, models


class CustomsLandedCostLine(models.Model):
    _name = 'customs.landed.cost.line'
    _description = 'Customs Duty Calculation Line'
    _order = 'landed_cost_id, product_id'

    landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='Landed Cost',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('type', 'in', ['product', 'consu'])],
    )
    hs_code_id = fields.Many2one(
        'customs.hs.code',
        string='HS Code',
        compute='_compute_hs_code',
        store=True,
    )
    quantity = fields.Float('Quantity', default=1.0, digits='Product Unit of Measure')

    # ── CIF inputs ───────────────────────────────────────────────────────────
    product_cost = fields.Monetary(
        'Product Cost',
        currency_field='currency_id',
    )
    freight = fields.Monetary(
        'Freight',
        currency_field='currency_id',
        help='Freight share allocated to this line. Auto-distributed from linked shipping bills.',
    )
    insurance = fields.Monetary(
        'Insurance',
        currency_field='currency_id',
        help='Insurance share allocated to this line. Auto-distributed from linked insurance bills.',
    )

    # ── CIF outputs (computed, stored) ───────────────────────────────────────
    cif_value = fields.Monetary(
        'CIF Value',
        currency_field='currency_id',
        compute='_compute_cif',
        store=True,
    )
    tax_base = fields.Monetary(
        'Tax Base',
        currency_field='currency_id',
        compute='_compute_cif',
        store=True,
        help='Base used for VAT/CESS/SSCL: CIF × 1.10 when the 10% uplift setting is enabled.',
    )

    # ── Duty outputs (computed, stored) ──────────────────────────────────────
    duty_rate_id = fields.Many2one(
        'customs.duty.rate',
        string='Applied Rate',
        readonly=True,
        help='The duty rate record that was used to compute this line.',
    )
    duty_amount = fields.Monetary(
        'Duty',
        currency_field='currency_id',
        compute='_compute_duties',
        store=True,
    )
    vat_amount = fields.Monetary(
        'VAT',
        currency_field='currency_id',
        compute='_compute_duties',
        store=True,
    )
    cess_amount = fields.Monetary(
        'CESS',
        currency_field='currency_id',
        compute='_compute_duties',
        store=True,
    )
    sscl_amount = fields.Monetary(
        'SSCL',
        currency_field='currency_id',
        compute='_compute_duties',
        store=True,
    )
    total_taxes = fields.Monetary(
        'Total Taxes',
        currency_field='currency_id',
        compute='_compute_duties',
        store=True,
    )

    # ── Override controls ────────────────────────────────────────────────────
    manual_override = fields.Boolean(
        'Manual Override',
        help='When enabled, CIF and duty values are locked and not recalculated automatically.',
    )
    override_reason = fields.Text('Override Reason')

    # ── Relational / currency helpers ────────────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        related='landed_cost_id.currency_id',
        store=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='landed_cost_id.company_id',
        store=True,
    )

    # ── Computed: HS Code resolution ─────────────────────────────────────────

    @api.depends(
        'product_id',
        'product_id.product_tmpl_id.hs_code_id',
        'product_id.product_tmpl_id.inherit_hs_from_category',
        'product_id.categ_id.hs_code_id',
    )
    def _compute_hs_code(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            if tmpl and not tmpl.inherit_hs_from_category and tmpl.hs_code_id:
                line.hs_code_id = tmpl.hs_code_id
            elif tmpl and tmpl.categ_id.hs_code_id:
                line.hs_code_id = tmpl.categ_id.hs_code_id
            else:
                line.hs_code_id = False

    # ── Computed: CIF value and tax base ─────────────────────────────────────

    @api.depends('product_cost', 'freight', 'insurance', 'manual_override')
    def _compute_cif(self):
        for line in self:
            if line.manual_override:
                continue
            cif = line.product_cost + line.freight + line.insurance
            company = line.company_id or self.env.company
            line.cif_value = cif
            line.tax_base = cif * 1.10 if company.customs_cif_uplift else cif

    # ── Computed: duty, VAT, CESS, SSCL ──────────────────────────────────────

    @api.depends(
        'cif_value',
        'tax_base',
        'hs_code_id',
        'manual_override',
        'landed_cost_id.country_of_origin_id',
    )
    def _compute_duties(self):
        rate_model = self.env['customs.duty.rate']
        today = fields.Date.today()
        for line in self:
            if line.manual_override:
                continue
            if not line.hs_code_id:
                line.duty_amount = 0.0
                line.vat_amount = 0.0
                line.cess_amount = 0.0
                line.sscl_amount = 0.0
                line.total_taxes = 0.0
                line.duty_rate_id = False
                continue
            company = line.company_id or self.env.company
            country_id = line.landed_cost_id.country_of_origin_id.id
            rate = rate_model.get_applicable_rate(
                line.hs_code_id.id, country_id, today, company.id
            )
            line.duty_rate_id = rate
            if rate:
                line.duty_amount = line.cif_value * rate.duty_rate / 100.0
                line.vat_amount = (
                    line.tax_base * rate.vat_rate / 100.0
                    if company.customs_enable_vat else 0.0
                )
                line.cess_amount = (
                    line.tax_base * rate.cess_rate / 100.0
                    if company.customs_enable_cess else 0.0
                )
                line.sscl_amount = (
                    line.tax_base * rate.sscl_rate / 100.0
                    if company.customs_enable_sscl else 0.0
                )
            else:
                line.duty_amount = 0.0
                line.vat_amount = 0.0
                line.cess_amount = 0.0
                line.sscl_amount = 0.0
            line.total_taxes = (
                line.duty_amount + line.vat_amount
                + line.cess_amount + line.sscl_amount
            )
