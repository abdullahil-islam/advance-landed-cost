from odoo import fields, models


class CustomsHsCode(models.Model):
    _name = 'customs.hs.code'
    _description = 'Harmonised System Code'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char('HS Code', required=True, index=True)
    description = fields.Text('Description')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        help='Leave empty to share this HS code across all companies.',
    )

    _sql_constraints = [
        ('name_company_unique', 'UNIQUE(name, company_id)',
         'An HS Code with this number already exists for this company.'),
    ]
