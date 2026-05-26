from odoo import fields, models


class CustomsDutyRegion(models.Model):
    _name = 'customs.duty.region'
    _description = 'Customs Duty Region'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char('Region Name', required=True)
    code = fields.Char(
        'Code',
        help='Short code used as a reference, e.g. EU, ASEAN, GCC.',
    )
    country_ids = fields.Many2many(
        'res.country',
        string='Member Countries',
        help='Countries that belong to this trade region. '
             'Used when looking up duty rates by region instead of individual country.',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        help='Leave empty to share this region across all companies.',
    )
