from odoo import fields, models


class CustomsDutyLevy(models.Model):
    _name = 'customs.duty.levy'
    _description = 'Customs Duty Levy Type'
    _rec_name = 'name'
    _order = 'levy_type, name'

    LEVY_TYPES = [
        ('vat', 'VAT'),
        ('cess', 'CESS'),
        ('sscl', 'SSCL'),
        ('custom', 'Custom Levy'),
    ]

    name = fields.Char('Levy Name', required=True)
    levy_type = fields.Selection(LEVY_TYPES, string='Type', required=True)
    rate = fields.Float('Rate (%)', digits=(5, 4))
    include_in_vat_base = fields.Boolean(
        'Include in VAT Base',
        help='Whether this levy is factored into the base used for VAT calculation.',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        help='Leave empty to share this levy definition across all companies.',
    )
