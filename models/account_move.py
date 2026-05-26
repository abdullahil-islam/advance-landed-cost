from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    customs_landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='Landed Cost',
        ondelete='set null',
        index=True,
        help='The advance landed cost record this bill belongs to.',
    )
    customs_bill_type = fields.Selection([
        ('customs', 'Customs Bill'),
        ('shipping', 'Shipping Bill'),
        ('insurance', 'Insurance Bill'),
        ('clearing', 'Clearing Bill'),
        ('journal_entry', 'Customs Journal Entry'),
    ], string='Customs Bill Type',
        help='Categorises this vendor bill within the customs landed cost workflow.',
    )
    # Foreign currency support: store original amount when bill is in a
    # different currency from the company's base currency.
    customs_amount_foreign = fields.Monetary(
        'Amount (Foreign Currency)',
        currency_field='customs_foreign_currency_id',
        help='Original bill amount in the foreign currency before conversion.',
    )
    customs_foreign_currency_id = fields.Many2one(
        'res.currency',
        string='Foreign Currency',
        help='The foreign currency this bill was issued in, if different from the company currency.',
    )
