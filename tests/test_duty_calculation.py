from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from .common import AdvanceLandedCostTestCommon


@tagged('post_install', '-at_install')
class TestDutyCalculation(AdvanceLandedCostTestCommon):

    def test_duty_formula_correct(self):
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        # duty_rate = 5% → duty = 1000 * 5/100 = 50
        self.assertAlmostEqual(line.duty_amount, 50.0, places=2)

    def test_vat_formula_correct(self):
        self.company.customs_enable_vat = True
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        # vat_rate = 20% on tax_base; uplift=False so tax_base=1000
        self.assertAlmostEqual(line.vat_amount, 200.0, places=2)

    def test_cess_formula_correct(self):
        self.company.customs_enable_cess = True
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        # cess_rate = 2% on tax_base = 1000
        self.assertAlmostEqual(line.cess_amount, 20.0, places=2)

    def test_vat_disabled_by_setting(self):
        self.company.customs_enable_vat = False
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        self.assertAlmostEqual(line.vat_amount, 0.0, places=2)
        self.company.customs_enable_vat = True

    def test_cess_disabled_by_setting(self):
        self.company.customs_enable_cess = False
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        self.assertAlmostEqual(line.cess_amount, 0.0, places=2)
        self.company.customs_enable_cess = True

    def test_total_taxes_sum(self):
        self.company.customs_enable_vat = True
        self.company.customs_enable_cess = True
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        expected = line.duty_amount + line.vat_amount + line.cess_amount + line.sscl_amount
        self.assertAlmostEqual(line.total_taxes, expected, places=2)

    def test_rate_not_found_returns_zero_duties(self):
        hs_unknown = self.env['customs.hs.code'].create({
            'name': 'TEST.UNKNOWN.00',
            'description': 'No rate defined for this',
            'company_id': False,
        })
        lc = self._make_lc()
        prod = self.env['product.product'].create({'name': 'Unknown Prod', 'type': 'consu'})
        prod.product_tmpl_id.write({'hs_code_id': hs_unknown.id,
                                    'inherit_hs_from_category': False})
        line = self._make_line(lc, prod, cost=500.0)
        self.assertAlmostEqual(line.duty_amount, 0.0, places=2)
        self.assertAlmostEqual(line.vat_amount, 0.0, places=2)

    def test_manual_override_echoes_override_fields(self):
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({
            'manual_override': True,
            'duty_amount_override': 99.0,
            'vat_amount_override': 199.0,
            'cess_amount_override': 9.0,
            'sscl_amount_override': 4.0,
        })
        self.assertAlmostEqual(line.duty_amount, 99.0, places=2)
        self.assertAlmostEqual(line.vat_amount, 199.0, places=2)
        self.assertAlmostEqual(line.cess_amount, 9.0, places=2)
        self.assertAlmostEqual(line.sscl_amount, 4.0, places=2)
        self.assertAlmostEqual(line.total_taxes, 311.0, places=2)

    def test_overlapping_date_constraint_raises(self):
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.OVERLAP.01',
            'company_id': False,
        })
        self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'country_id': self.country_de.id,
            'date_from': '2023-01-01',
            'date_to': '2023-12-31',
            'duty_rate': 5.0,
            'company_id': False,
        })
        with self.assertRaises(ValidationError):
            self.env['customs.duty.rate'].create({
                'hs_code_id': hs.id,
                'country_id': self.country_de.id,
                'date_from': '2023-06-01',
                'date_to': '2024-01-31',
                'duty_rate': 7.0,
                'company_id': False,
            })

    def test_country_region_exclusive_constraint(self):
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.EXCLUSIVE.01',
            'company_id': False,
        })
        region = self.env['customs.duty.region'].create({
            'name': 'Test Region',
            'company_id': False,
        })
        with self.assertRaises(ValidationError):
            self.env['customs.duty.rate'].create({
                'hs_code_id': hs.id,
                'country_id': self.country_de.id,
                'region_id': region.id,
                'date_from': '2020-01-01',
                'duty_rate': 5.0,
                'company_id': False,
            })

    def test_rate_priority_country_beats_region(self):
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.PRIORITY.01',
            'company_id': False,
        })
        region = self.env['customs.duty.region'].create({
            'name': 'Priority Test Region',
            'country_ids': [(4, self.country_de.id)],
            'company_id': False,
        })
        region_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'region_id': region.id,
            'date_from': '2020-01-01',
            'duty_rate': 3.0,
            'company_id': False,
        })
        country_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'country_id': self.country_de.id,
            'date_from': '2020-01-01',
            'duty_rate': 8.0,
            'company_id': False,
        })
        found = self.env['customs.duty.rate'].get_applicable_rate(
            hs.id, self.country_de.id, fields.Date.today(), self.company.id
        )
        self.assertEqual(found.id, country_rate.id,
                         "Country-specific rate must take priority over region rate")

    def test_rate_priority_region_beats_global(self):
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.PRIORITY.02',
            'company_id': False,
        })
        region = self.env['customs.duty.region'].create({
            'name': 'Region Beats Global',
            'country_ids': [(4, self.country_de.id)],
            'company_id': False,
        })
        global_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'date_from': '2020-01-01',
            'duty_rate': 2.0,
            'company_id': False,
        })
        region_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'region_id': region.id,
            'date_from': '2020-01-01',
            'duty_rate': 6.0,
            'company_id': False,
        })
        found = self.env['customs.duty.rate'].get_applicable_rate(
            hs.id, self.country_de.id, fields.Date.today(), self.company.id
        )
        self.assertEqual(found.id, region_rate.id,
                         "Region rate must take priority over global default")

    def test_global_fallback_when_no_country_rate(self):
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.GLOBAL.01',
            'company_id': False,
        })
        global_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'date_from': '2020-01-01',
            'duty_rate': 10.0,
            'company_id': False,
        })
        found = self.env['customs.duty.rate'].get_applicable_rate(
            hs.id, self.country_fr.id, fields.Date.today(), self.company.id
        )
        self.assertEqual(found.id, global_rate.id,
                         "Global rate should be returned when no country/region match exists")
