from odoo import api, fields, models
from odoo.exceptions import UserError


class CustomsDutyOverrideLog(models.Model):
    _name = 'customs.duty.override.log'
    _description = 'Duty Override Audit Log'
    _order = 'timestamp desc'
    _rec_name = 'timestamp'

    landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='Landed Cost',
        required=True,
        ondelete='cascade',
        index=True,
    )
    line_id = fields.Many2one(
        'customs.landed.cost.line',
        string='Line',
        required=True,
        ondelete='cascade',
    )
    old_duty = fields.Monetary('Previous Duty', currency_field='currency_id')
    new_duty = fields.Monetary('New Duty', currency_field='currency_id')
    reason = fields.Text('Reason', required=True)
    user_id = fields.Many2one(
        'res.users',
        string='Changed By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    timestamp = fields.Datetime(
        'Timestamp',
        default=fields.Datetime.now,
        readonly=True,
    )
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

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group('advance_landed_cost.group_customs_manager'):
            raise UserError(
                "Only Customs Managers can record duty overrides."
            )
        return super().create(vals_list)
