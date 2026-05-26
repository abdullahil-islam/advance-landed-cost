from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    # ── Reference & workflow state ────────────────────────────────────────────
    customs_reference = fields.Char(
        'Customs Reference',
        readonly=True,
        copy=False,
        default='New',
        index=True,
    )
    customs_state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('done', 'Done'),
    ], string='Customs Status', default='draft', tracking=True, copy=False)

    # ── Origin & split configuration ──────────────────────────────────────────
    country_of_origin_id = fields.Many2one(
        'res.country',
        string='Country of Origin',
        help='Default country of origin for duty rate lookup on all lines.',
    )
    cif_split_method = fields.Selection([
        ('by_quantity', 'By Quantity'),
        ('by_weight', 'By Weight'),
        ('by_volume', 'By Volume'),
        ('by_current_cost', 'By Current Cost'),
        ('equal', 'Equal'),
    ], string='CIF Split Method', default='by_current_cost',
        help='Method used to distribute freight and insurance across product lines.',
    )

    # ── Customs calculation lines ─────────────────────────────────────────────
    customs_line_ids = fields.One2many(
        'customs.landed.cost.line',
        'landed_cost_id',
        string='Duty Calculation Lines',
    )

    # ── Linked bills ──────────────────────────────────────────────────────────
    customs_bill_ids = fields.One2many(
        'account.move',
        'customs_landed_cost_id',
        string='Customs Bills',
        domain=[('customs_bill_type', '=', 'customs')],
    )
    shipping_bill_ids = fields.One2many(
        'account.move',
        'customs_landed_cost_id',
        string='Shipping Bills',
        domain=[('customs_bill_type', '=', 'shipping')],
    )
    insurance_bill_ids = fields.One2many(
        'account.move',
        'customs_landed_cost_id',
        string='Insurance Bills',
        domain=[('customs_bill_type', '=', 'insurance')],
    )

    # ── Bill summary (computed) ───────────────────────────────────────────────
    customs_bill_count = fields.Integer(
        'Customs Bill Count',
        compute='_compute_bill_summary',
    )
    shipping_bill_count = fields.Integer(
        'Shipping Bill Count',
        compute='_compute_bill_summary',
    )
    insurance_bill_count = fields.Integer(
        'Insurance Bill Count',
        compute='_compute_bill_summary',
    )
    bills_payment_state = fields.Selection([
        ('all_paid', 'All Bills Paid'),
        ('partial', 'Partially Paid'),
        ('not_paid', 'Bills Unpaid'),
        ('no_bills', 'No Bills'),
    ], string='Bills Status', compute='_compute_bill_summary',
        help='Aggregate payment status across all linked customs, shipping, and insurance bills.',
    )

    # ── Audit logs ────────────────────────────────────────────────────────────
    cif_override_log_ids = fields.One2many(
        'customs.cif.override.log',
        'landed_cost_id',
        string='CIF Override Log',
        readonly=True,
    )
    duty_override_log_ids = fields.One2many(
        'customs.duty.override.log',
        'landed_cost_id',
        string='Duty Override Log',
        readonly=True,
    )

    # ── Running totals ────────────────────────────────────────────────────────
    total_product_cost = fields.Monetary(
        'Total Product Cost',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    total_freight = fields.Monetary(
        'Total Freight',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    total_insurance = fields.Monetary(
        'Total Insurance',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    total_cif = fields.Monetary(
        'Total CIF',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    total_duty = fields.Monetary(
        'Total Duty',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    total_vat = fields.Monetary(
        'Total VAT',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    total_cess = fields.Monetary(
        'Total CESS',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    total_sscl = fields.Monetary(
        'Total SSCL',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
    )
    grand_total = fields.Monetary(
        'Grand Total',
        compute='_compute_customs_totals',
        store=True,
        currency_field='currency_id',
        help='Total landed cost: product cost + freight + insurance + all duties and taxes.',
    )

    # ── ORM overrides ─────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('customs_reference', 'New') == 'New':
                vals['customs_reference'] = (
                    self.env['ir.sequence'].next_by_code('advance.landed.cost')
                    or 'New'
                )
        return super().create(vals_list)

    def write(self, vals):
        locked_states = ('approved', 'done')
        for record in self:
            if record.customs_state in locked_states:
                # Only allow chatter and system fields through
                allowed = {
                    'message_ids', 'activity_ids',
                    'message_main_attachment_id',
                }
                protected = set(vals.keys()) - allowed
                if protected and not self.env.context.get('bypass_lock'):
                    raise UserError(
                        f"Record '{record.customs_reference}' is locked in "
                        f"'{record.customs_state}' state and cannot be edited. "
                        f"Contact a Finance Manager to unlock."
                    )
        return super().write(vals)

    # ── Computed: bill counts + aggregate payment status ─────────────────────

    @api.depends(
        'customs_bill_ids', 'shipping_bill_ids', 'insurance_bill_ids',
        'customs_bill_ids.payment_state',
        'shipping_bill_ids.payment_state',
        'insurance_bill_ids.payment_state',
    )
    def _compute_bill_summary(self):
        for lc in self:
            lc.customs_bill_count = len(lc.customs_bill_ids)
            lc.shipping_bill_count = len(lc.shipping_bill_ids)
            lc.insurance_bill_count = len(lc.insurance_bill_ids)
            all_bills = lc.customs_bill_ids | lc.shipping_bill_ids | lc.insurance_bill_ids
            if not all_bills:
                lc.bills_payment_state = 'no_bills'
            elif all(
                b.payment_state in ('paid', 'in_payment') for b in all_bills
            ):
                lc.bills_payment_state = 'all_paid'
            elif any(
                b.payment_state in ('paid', 'in_payment', 'partial')
                for b in all_bills
            ):
                lc.bills_payment_state = 'partial'
            else:
                lc.bills_payment_state = 'not_paid'

    # ── Computed totals ───────────────────────────────────────────────────────

    @api.depends(
        'customs_line_ids.product_cost',
        'customs_line_ids.freight',
        'customs_line_ids.insurance',
        'customs_line_ids.cif_value',
        'customs_line_ids.duty_amount',
        'customs_line_ids.vat_amount',
        'customs_line_ids.cess_amount',
        'customs_line_ids.sscl_amount',
    )
    def _compute_customs_totals(self):
        for lc in self:
            lines = lc.customs_line_ids
            lc.total_product_cost = sum(lines.mapped('product_cost'))
            lc.total_freight = sum(lines.mapped('freight'))
            lc.total_insurance = sum(lines.mapped('insurance'))
            lc.total_cif = sum(lines.mapped('cif_value'))
            lc.total_duty = sum(lines.mapped('duty_amount'))
            lc.total_vat = sum(lines.mapped('vat_amount'))
            lc.total_cess = sum(lines.mapped('cess_amount'))
            lc.total_sscl = sum(lines.mapped('sscl_amount'))
            lc.grand_total = (
                lc.total_product_cost + lc.total_freight + lc.total_insurance
                + lc.total_duty + lc.total_vat + lc.total_cess + lc.total_sscl
            )

    # ── State machine ─────────────────────────────────────────────────────────

    def action_confirm(self):
        for record in self:
            if record.customs_state != 'draft':
                raise UserError("Only draft records can be confirmed.")
            record._validate_hs_codes()
            record._check_missing_rates()
        self.write({'customs_state': 'confirmed'})

    def action_approve(self):
        if not self.env.user.has_group('advance_landed_cost.group_finance_manager'):
            raise UserError("Only Finance Managers can approve landed costs.")
        for record in self:
            if record.customs_state != 'confirmed':
                raise UserError("Only confirmed records can be approved.")
        self.write({'customs_state': 'approved'})

    def action_validate_customs(self):
        """
        Validate the landed cost: run Odoo's standard inventory valuation,
        then post custom duty journal entries (Phase 8) and lock the record.
        """
        self.ensure_one()
        if self.customs_state != 'approved':
            raise UserError(
                "The landed cost must be approved before it can be validated."
            )
        # Phase 8 will add: super().button_validate() and
        # self._create_customs_journal_entries() here.
        self.with_context(bypass_lock=True).write({'customs_state': 'done'})

    def action_reset_to_draft(self):
        if not self.env.user.has_group('advance_landed_cost.group_finance_manager'):
            raise UserError("Only Finance Managers can reset to draft.")
        for record in self:
            if record.customs_state == 'done':
                raise UserError("Done records cannot be reset.")
        self.with_context(bypass_lock=True).write({'customs_state': 'draft'})

    def _validate_hs_codes(self):
        """Raise if any customs line is missing an HS code."""
        missing = self.customs_line_ids.filtered(lambda l: not l.hs_code_id)
        if missing:
            names = ', '.join(missing.mapped('product_id.display_name'))
            raise ValidationError(
                f"The following products are missing an HS Code: {names}\n"
                f"Please assign HS codes before confirming."
            )

    def _check_missing_rates(self):
        """Post a warning on the chatter for lines with no applicable duty rate."""
        rate_model = self.env['customs.duty.rate']
        today = fields.Date.today()
        company = self.company_id or self.env.company
        country_id = self.country_of_origin_id.id
        missing = []
        for line in self.customs_line_ids.filtered(
            lambda l: l.hs_code_id and not l.manual_override
        ):
            rate = rate_model.get_applicable_rate(
                line.hs_code_id.id, country_id, today, company.id
            )
            if not rate:
                missing.append(line.product_id.display_name)
        if missing:
            self.message_post(
                body=(
                    "⚠ No duty rate found for the following products — "
                    "duty will be calculated as zero: "
                    + ", ".join(missing)
                )
            )

    # ── CIF Distribution Engine (Phase 5) ────────────────────────────────────

    def action_open_recalculate_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'customs.recalculate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_landed_cost_id': self.id},
        }

    def _distribute_cif(self):
        """
        Distribute freight and insurance from linked bills across all
        non-overridden customs lines using the configured split method.

        Overridden lines (manual_override=True) are skipped; their
        freight and insurance values are left untouched.
        """
        self.ensure_one()
        lines = self.customs_line_ids.filtered(lambda l: not l.manual_override)
        if not lines:
            return

        total_freight = sum(self.shipping_bill_ids.mapped('amount_untaxed'))
        total_insurance = sum(self.insurance_bill_ids.mapped('amount_untaxed'))

        weights = self._compute_split_weights(lines, self.cif_split_method)
        total_weight = sum(weights.values()) or 1.0

        for line in lines:
            ratio = weights.get(line.id, 0.0) / total_weight
            line.write({
                'freight': total_freight * ratio,
                'insurance': total_insurance * ratio,
            })

    def _compute_split_weights(self, lines, method):
        """
        Return a dict {line.id: weight} for the given split method.

        Falls back to equal share when all computed weights are zero
        (e.g. all products have weight=0 for the 'by_weight' method).
        """
        weights = {}
        for line in lines:
            qty = line.quantity or 1.0
            if method == 'by_quantity':
                weights[line.id] = qty
            elif method == 'by_weight':
                weights[line.id] = (line.product_id.weight or 0.0) * qty
            elif method == 'by_volume':
                weights[line.id] = (line.product_id.volume or 0.0) * qty
            elif method == 'by_current_cost':
                weights[line.id] = line.product_cost or 1.0
            else:  # 'equal' and any unrecognised value
                weights[line.id] = 1.0

        # Guard: if every weight is zero, fall back to equal distribution
        if not any(weights.values()):
            weights = {lid: 1.0 for lid in weights}

        return weights

    def action_open_duty_override_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'customs.duty.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_landed_cost_id': self.id},
        }

    # ── Bill generation ───────────────────────────────────────────────────────

    def action_generate_customs_bill(self):
        self.ensure_one()
        return self._generate_bill('customs')

    def action_generate_shipping_bill(self):
        self.ensure_one()
        return self._generate_bill('shipping')

    def action_generate_insurance_bill(self):
        self.ensure_one()
        return self._generate_bill('insurance')

    def _generate_bill(self, bill_type):
        """
        Create a vendor bill pre-filled with duty/cost lines and open it.

        If the landed cost currency differs from the company's base currency,
        the bill is created in the landed cost currency and the original amount
        is also stored in customs_amount_foreign for reference.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        currency = self.currency_id or company.currency_id

        bill_vals = {
            'move_type': 'in_invoice',
            'customs_landed_cost_id': self.id,
            'customs_bill_type': bill_type,
            'invoice_line_ids': self._build_bill_lines(bill_type, company),
        }
        if currency != company.currency_id:
            bill_vals['currency_id'] = currency.id

        bill = self.env['account.move'].create(bill_vals)

        if currency != company.currency_id:
            bill.write({
                'customs_amount_foreign': bill.amount_untaxed,
                'customs_foreign_currency_id': currency.id,
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _build_bill_lines(self, bill_type, company):
        """
        Return a list of Command.create dicts for the invoice_line_ids of
        the new bill.  Lines with zero amount are skipped.
        """
        def _line(name, amount, account):
            if not amount:
                return None
            vals = {'name': name, 'price_unit': amount, 'quantity': 1.0}
            if account:
                vals['account_id'] = account.id
            return Command.create(vals)

        if bill_type == 'customs':
            entries = [
                ('Customs Duty', self.total_duty,
                 company.customs_duty_payable_account_id),
                ('Import VAT', self.total_vat,
                 company.customs_vat_payable_account_id),
                ('CESS', self.total_cess,
                 company.customs_duty_payable_account_id),
                ('SSCL', self.total_sscl,
                 company.customs_duty_payable_account_id),
            ]
            return [cmd for name, amt, acc in entries
                    if (cmd := _line(name, amt, acc))]

        if bill_type == 'shipping':
            cmd = _line('Freight / Shipping', self.total_freight,
                        company.customs_freight_payable_account_id)
            return [cmd] if cmd else []

        if bill_type == 'insurance':
            cmd = _line('Insurance', self.total_insurance,
                        company.customs_insurance_payable_account_id)
            return [cmd] if cmd else []

        return []

    # ── Stat-button actions ───────────────────────────────────────────────────

    def action_view_customs_bills(self):
        self.ensure_one()
        return self._bill_action('Customs Bills', 'customs')

    def action_view_shipping_bills(self):
        self.ensure_one()
        return self._bill_action('Shipping Bills', 'shipping')

    def action_view_insurance_bills(self):
        self.ensure_one()
        return self._bill_action('Insurance Bills', 'insurance')

    def _bill_action(self, name, bill_type):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('customs_landed_cost_id', '=', self.id),
                ('customs_bill_type', '=', bill_type),
            ],
            'context': {
                'default_customs_landed_cost_id': self.id,
                'default_customs_bill_type': bill_type,
                'default_move_type': 'in_invoice',
            },
        }
