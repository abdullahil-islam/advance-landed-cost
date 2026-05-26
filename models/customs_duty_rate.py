from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CustomsDutyRate(models.Model):
    _name = 'customs.duty.rate'
    _description = 'Customs Duty Rate'
    _order = 'hs_code_id, date_from desc'

    hs_code_id = fields.Many2one(
        'customs.hs.code',
        string='HS Code',
        required=True,
        index=True,
        ondelete='restrict',
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country of Origin',
        help='Set for a country-specific rate. '
             'Leave empty when using a region or a global default.',
    )
    region_id = fields.Many2one(
        'customs.duty.region',
        string='Trade Region',
        help='Set for a region-wide rate. '
             'Leave empty when using a specific country or a global default.',
    )
    scope_display = fields.Char(
        'Scope',
        compute='_compute_scope_display',
        store=False,
        help='Human-readable summary of whether this rate applies to a country, region, or globally.',
    )
    date_from = fields.Date('Valid From', required=True)
    date_to = fields.Date(
        'Valid To',
        help='Leave empty for an open-ended rate that never expires.',
    )
    duty_rate = fields.Float('Duty Rate (%)', digits=(5, 4))
    vat_rate = fields.Float('VAT Rate (%)', digits=(5, 4))
    cess_rate = fields.Float('CESS Rate (%)', digits=(5, 4))
    sscl_rate = fields.Float('SSCL Rate (%)', digits=(5, 4))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        help='Leave empty for a global rate applicable to all companies. '
             'Company-specific rates take priority over global ones during lookup.',
    )
    notes = fields.Text('Notes')

    @api.depends('country_id', 'region_id')
    def _compute_scope_display(self):
        for rate in self:
            if rate.country_id:
                rate.scope_display = rate.country_id.name
            elif rate.region_id:
                rate.scope_display = f'Region: {rate.region_id.name}'
            else:
                rate.scope_display = 'Global Default'

    # ── Constraints ──────────────────────────────────────────────────────────

    @api.constrains('country_id', 'region_id')
    def _check_country_region_exclusive(self):
        for rate in self:
            if rate.country_id and rate.region_id:
                raise ValidationError(
                    "A duty rate cannot target both a specific country and a region "
                    "at the same time. Please set either Country or Region, not both."
                )

    @api.constrains(
        'date_from', 'date_to',
        'hs_code_id', 'country_id', 'region_id',
        'company_id', 'active',
    )
    def _check_no_overlapping_dates(self):
        for rate in self:
            if not rate.active:
                continue
            conflict = self._find_overlapping(rate)
            if conflict:
                scope = (
                    f"country '{conflict.country_id.name}'"
                    if conflict.country_id
                    else f"region '{conflict.region_id.name}'"
                    if conflict.region_id
                    else "global default"
                )
                raise ValidationError(
                    f"This rate for HS Code '{rate.hs_code_id.name}' ({scope}) "
                    f"overlaps with an existing rate (ID {conflict.id}). "
                    f"Adjust the date range to remove the conflict."
                )

    def _find_overlapping(self, rate):
        """Return the first rate that overlaps with the given rate, or empty recordset."""
        domain = [
            ('id', '!=', rate.id),
            ('hs_code_id', '=', rate.hs_code_id.id),
            ('country_id', '=', rate.country_id.id),
            ('region_id', '=', rate.region_id.id),
            ('active', '=', True),
            '|',
                ('company_id', '=', False),
                ('company_id', '=', rate.company_id.id if rate.company_id else False),
        ]
        for existing in self.search(domain):
            if self._dates_overlap(rate, existing):
                return existing
        return self.browse()

    @staticmethod
    def _dates_overlap(r1, r2):
        max_date = fields.Date.from_string('9999-12-31')
        r1_to = r1.date_to or max_date
        r2_to = r2.date_to or max_date
        return r1.date_from <= r2_to and r2.date_from <= r1_to

    # ── Rate Lookup Engine ────────────────────────────────────────────────────

    @api.model
    def get_applicable_rate(self, hs_code_id, country_id, date, company_id):
        """
        Return the most specific applicable duty rate record for a given
        HS code, country of origin, and date.

        Lookup priority:
          1. Exact country + HS code  (company-specific beats global)
          2. Region containing the country + HS code
          3. Global default (no country, no region) + HS code
        Returns an empty recordset when no rate is found.
        """
        base_domain = [
            ('hs_code_id', '=', hs_code_id),
            ('date_from', '<=', date),
            '|', ('date_to', '=', False), ('date_to', '>=', date),
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company_id),
        ]
        order = 'company_id desc nulls last, id desc'

        if country_id:
            # 1. Exact country match
            rate = self.search(
                base_domain + [
                    ('country_id', '=', country_id),
                    ('region_id', '=', False),
                ],
                limit=1,
                order=order,
            )
            if rate:
                return rate

            # 2. Region that contains this country
            regions = self.env['customs.duty.region'].search(
                [('country_ids', 'in', [country_id])]
            )
            if regions:
                rate = self.search(
                    base_domain + [
                        ('region_id', 'in', regions.ids),
                        ('country_id', '=', False),
                    ],
                    limit=1,
                    order=order,
                )
                if rate:
                    return rate

        # 3. Global default
        return self.search(
            base_domain + [
                ('country_id', '=', False),
                ('region_id', '=', False),
            ],
            limit=1,
            order=order,
        )
