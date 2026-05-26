from odoo import api, fields, models
from odoo.exceptions import UserError


class CustomsRecalculateWizard(models.TransientModel):
    _name = 'customs.recalculate.wizard'
    _description = 'Recalculate CIF and Duties'

    landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='Landed Cost',
        required=True,
        readonly=True,
    )
    reason = fields.Text(
        'Reason for Recalculation',
        required=True,
        help='Mandatory reason stored in the CIF override audit log for every '
             'line whose manual override is cleared.',
    )
    reset_overrides = fields.Boolean(
        'Reset Manual Overrides',
        default=True,
        help='Clear the manual override flag on all lines so that CIF values '
             'are re-distributed automatically. Uncheck to redistribute only '
             'lines that are not already overridden.',
    )
    overridden_line_count = fields.Integer(
        'Lines with Manual Override',
        compute='_compute_overridden_line_count',
    )

    @api.depends('landed_cost_id')
    def _compute_overridden_line_count(self):
        for wizard in self:
            wizard.overridden_line_count = len(
                wizard.landed_cost_id.customs_line_ids.filtered('manual_override')
            )

    def action_recalculate(self):
        self.ensure_one()
        lc = self.landed_cost_id

        if lc.customs_state in ('approved', 'done'):
            raise UserError(
                "CIF cannot be recalculated on a locked landed cost. "
                "Reset it to Draft first."
            )

        if self.reset_overrides:
            overridden = lc.customs_line_ids.filtered('manual_override')
            if overridden:
                if not self.env.user.has_group(
                    'advance_landed_cost.group_customs_manager'
                ):
                    raise UserError(
                        "Clearing manual overrides requires Customs Manager access."
                    )
                # Write audit log entries before clearing the override
                log_vals = []
                for line in overridden:
                    log_vals.append({
                        'landed_cost_id': lc.id,
                        'line_id': line.id,
                        'old_cif': line.cif_value,
                        'new_cif': 0.0,  # will be recomputed after distribution
                        'reason': self.reason,
                    })
                self.env['customs.cif.override.log'].create(log_vals)
                overridden.write({'manual_override': False, 'override_reason': False})

        lc._distribute_cif()
        return {'type': 'ir.actions.act_window_close'}
