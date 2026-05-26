from odoo import api, fields, models
from odoo.exceptions import UserError


class CustomsDutyOverrideWizard(models.TransientModel):
    _name = 'customs.duty.override.wizard'
    _description = 'Manual Duty Override Wizard'

    landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='Landed Cost',
        required=True,
        readonly=True,
    )
    line_id = fields.Many2one(
        'customs.landed.cost.line',
        string='Line',
        required=True,
        domain="[('landed_cost_id', '=', landed_cost_id)]",
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='landed_cost_id.currency_id',
    )

    # Read-only current values shown for comparison
    current_duty = fields.Monetary(
        'Current Duty',
        currency_field='currency_id',
        compute='_compute_current_values',
    )
    current_vat = fields.Monetary(
        'Current VAT',
        currency_field='currency_id',
        compute='_compute_current_values',
    )
    current_cess = fields.Monetary(
        'Current CESS',
        currency_field='currency_id',
        compute='_compute_current_values',
    )
    current_sscl = fields.Monetary(
        'Current SSCL',
        currency_field='currency_id',
        compute='_compute_current_values',
    )
    current_total = fields.Monetary(
        'Current Total',
        currency_field='currency_id',
        compute='_compute_current_values',
    )

    # New override values
    new_duty = fields.Monetary('New Duty', currency_field='currency_id')
    new_vat = fields.Monetary('New VAT', currency_field='currency_id')
    new_cess = fields.Monetary('New CESS', currency_field='currency_id')
    new_sscl = fields.Monetary('New SSCL', currency_field='currency_id')
    new_total = fields.Monetary(
        'New Total',
        currency_field='currency_id',
        compute='_compute_new_total',
    )

    reason = fields.Text('Reason', required=True)

    @api.depends('line_id')
    def _compute_current_values(self):
        for wizard in self:
            line = wizard.line_id
            if line:
                wizard.current_duty = line.duty_amount
                wizard.current_vat = line.vat_amount
                wizard.current_cess = line.cess_amount
                wizard.current_sscl = line.sscl_amount
                wizard.current_total = line.total_taxes
            else:
                wizard.current_duty = 0.0
                wizard.current_vat = 0.0
                wizard.current_cess = 0.0
                wizard.current_sscl = 0.0
                wizard.current_total = 0.0

    @api.depends('new_duty', 'new_vat', 'new_cess', 'new_sscl')
    def _compute_new_total(self):
        for wizard in self:
            wizard.new_total = (
                wizard.new_duty + wizard.new_vat
                + wizard.new_cess + wizard.new_sscl
            )

    @api.onchange('line_id')
    def _onchange_line_id(self):
        if self.line_id:
            self.new_duty = self.line_id.duty_amount
            self.new_vat = self.line_id.vat_amount
            self.new_cess = self.line_id.cess_amount
            self.new_sscl = self.line_id.sscl_amount

    def action_apply_override(self):
        self.ensure_one()

        if not self.env.user.has_group('advance_landed_cost.group_customs_manager'):
            raise UserError("Manual duty overrides require Customs Manager access.")

        lc = self.landed_cost_id
        if lc.customs_state in ('approved', 'done'):
            raise UserError(
                "Duty overrides cannot be applied to a locked landed cost. "
                "Reset it to Draft first."
            )

        line = self.line_id
        self.env['customs.duty.override.log'].create({
            'landed_cost_id': lc.id,
            'line_id': line.id,
            'old_duty': line.duty_amount,
            'new_duty': self.new_duty,
            'reason': self.reason,
        })

        line.with_context(bypass_lock=True).write({
            'manual_override': True,
            'override_reason': self.reason,
            'duty_amount_override': self.new_duty,
            'vat_amount_override': self.new_vat,
            'cess_amount_override': self.new_cess,
            'sscl_amount_override': self.new_sscl,
        })

        return {'type': 'ir.actions.act_window_close'}
