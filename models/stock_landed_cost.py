from odoo import api, fields, models
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

    # ── Bill generation (Phase 7 adds full implementation) ───────────────────

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
        """Stub — full implementation in Phase 7."""
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'customs_landed_cost_id': self.id,
            'customs_bill_type': bill_type,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }
