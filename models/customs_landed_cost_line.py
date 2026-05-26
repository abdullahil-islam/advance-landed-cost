from odoo import api, fields, models
from odoo.exceptions import UserError


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

    # ── Manual CIF override ──────────────────────────────────────────────────
    # When manual_override=True, _compute_cif uses cif_override instead of
    # product_cost + freight + insurance. The user sets cif_override directly.
    cif_override = fields.Monetary(
        'Manual CIF',
        currency_field='currency_id',
        help='CIF value entered manually. Active only when Manual Override is enabled.',
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

    # ── Manual duty override values ───────────────────────────────────────────
    # When manual_override=True, _compute_duties outputs these stored values
    # instead of recalculating from the rate table. The duty override wizard
    # writes here; the computed duty_amount/vat_amount/etc. fields just echo them.
    duty_amount_override = fields.Monetary(
        'Override Duty',
        currency_field='currency_id',
        help='Manually set duty amount. Active only when Manual Override is enabled.',
    )
    vat_amount_override = fields.Monetary(
        'Override VAT',
        currency_field='currency_id',
    )
    cess_amount_override = fields.Monetary(
        'Override CESS',
        currency_field='currency_id',
    )
    sscl_amount_override = fields.Monetary(
        'Override SSCL',
        currency_field='currency_id',
    )

    # ── Duty outputs (computed, stored) ──────────────────────────────────────
    duty_rate_id = fields.Many2one(
        'customs.duty.rate',
        string='Applied Rate',
        readonly=True,
        help='The duty rate record used to compute this line. Empty when manual override is active.',
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
        help='When enabled, CIF and duty values are taken from the override fields '
             'instead of being recalculated automatically.',
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

    # ── ORM: write guard ─────────────────────────────────────────────────────

    def write(self, vals):
        if not self.env.context.get('bypass_lock'):
            locked = self.filtered(
                lambda l: l.landed_cost_id.customs_state in ('approved', 'done')
            )
            if locked:
                names = ', '.join(locked.mapped('product_id.display_name'))
                raise UserError(
                    f"The following lines are locked because the landed cost is "
                    f"in Approved or Done state: {names}"
                )
        return super().write(vals)

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
    # When manual_override=True  → use cif_override as the CIF value.
    # When manual_override=False → compute CIF from product_cost + freight + insurance.

    @api.depends(
        'product_cost', 'freight', 'insurance',
        'manual_override', 'cif_override',
    )
    def _compute_cif(self):
        for line in self:
            cif = line.cif_override if line.manual_override else (
                line.product_cost + line.freight + line.insurance
            )
            company = line.company_id or self.env.company
            line.cif_value = cif
            line.tax_base = cif * 1.10 if company.customs_cif_uplift else cif

    # ── Computed: duty, VAT, CESS, SSCL ──────────────────────────────────────
    # When manual_override=True  → echo the *_override fields as the outputs.
    # When manual_override=False → look up the rate table and calculate.

    @api.depends(
        'cif_value', 'tax_base', 'hs_code_id', 'manual_override',
        'duty_amount_override', 'vat_amount_override',
        'cess_amount_override', 'sscl_amount_override',
        'landed_cost_id.country_of_origin_id',
    )
    def _compute_duties(self):
        rate_model = self.env['customs.duty.rate']
        today = fields.Date.today()
        for line in self:
            if line.manual_override:
                line.duty_amount = line.duty_amount_override
                line.vat_amount = line.vat_amount_override
                line.cess_amount = line.cess_amount_override
                line.sscl_amount = line.sscl_amount_override
                line.total_taxes = (
                    line.duty_amount_override + line.vat_amount_override
                    + line.cess_amount_override + line.sscl_amount_override
                )
                line.duty_rate_id = False
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
