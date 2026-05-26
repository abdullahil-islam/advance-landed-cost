from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from .common import AdvanceLandedCostTestCommon


@tagged('post_install', '-at_install')
class TestMultiCompany(AdvanceLandedCostTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env['res.company'].create({'name': 'Test Company B'})

    def test_company_specific_rate_beats_global(self):
        """A company-specific rate takes priority over a global rate with the same scope."""
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.MC.01',
            'company_id': False,
        })
        global_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'country_id': self.country_de.id,
            'date_from': '2020-01-01',
            'duty_rate': 3.0,
            'company_id': False,
        })
        company_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'country_id': self.country_de.id,
            'date_from': '2020-01-01',
            'duty_rate': 7.0,
            'company_id': self.company.id,
        })
        found = self.env['customs.duty.rate'].get_applicable_rate(
            hs.id, self.country_de.id, fields.Date.today(), self.company.id
        )
        self.assertEqual(found.id, company_rate.id,
                         "Company-specific rate must take priority over global rate")

    def test_global_rate_visible_to_all_companies(self):
        """A global rate (company_id=False) is returned for any company."""
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.MC.02',
            'company_id': False,
        })
        global_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'country_id': self.country_de.id,
            'date_from': '2020-01-01',
            'duty_rate': 5.0,
            'company_id': False,
        })
        found_a = self.env['customs.duty.rate'].get_applicable_rate(
            hs.id, self.country_de.id, fields.Date.today(), self.company.id
        )
        found_b = self.env['customs.duty.rate'].get_applicable_rate(
            hs.id, self.country_de.id, fields.Date.today(), self.company_b.id
        )
        self.assertEqual(found_a.id, global_rate.id)
        self.assertEqual(found_b.id, global_rate.id,
                         "Global rate must be accessible from Company B")

    def test_company_a_rate_not_returned_for_company_b(self):
        """A company-specific rate for Company A must not be returned for Company B."""
        hs = self.env['customs.hs.code'].create({
            'name': 'TEST.MC.03',
            'company_id': False,
        })
        company_a_rate = self.env['customs.duty.rate'].create({
            'hs_code_id': hs.id,
            'country_id': self.country_de.id,
            'date_from': '2020-01-01',
            'duty_rate': 7.0,
            'company_id': self.company.id,
        })
        found_b = self.env['customs.duty.rate'].get_applicable_rate(
            hs.id, self.country_de.id, fields.Date.today(), self.company_b.id
        )
        self.assertFalse(
            found_b,
            "Company A's rate must not be visible when looking up for Company B"
        )

    def test_approved_state_blocks_write(self):
        """Writes to a landed cost in 'approved' state raise UserError."""
        lc = self._make_lc()
        lc.with_context(bypass_lock=True).write({'customs_state': 'approved'})
        with self.assertRaises(UserError):
            lc.write({'cif_split_method': 'equal'})

    def test_done_state_blocks_write(self):
        """Writes to a landed cost in 'done' state raise UserError."""
        lc = self._make_lc()
        lc.with_context(bypass_lock=True).write({'customs_state': 'done'})
        with self.assertRaises(UserError):
            lc.write({'cif_split_method': 'equal'})

    def test_bypass_lock_allows_write_in_approved(self):
        """bypass_lock context flag lets authorised code write to locked records."""
        lc = self._make_lc()
        lc.with_context(bypass_lock=True).write({'customs_state': 'approved'})
        lc.with_context(bypass_lock=True).write({'cif_split_method': 'equal'})
        self.assertEqual(lc.cif_split_method, 'equal')

    def test_line_write_guard_in_approved_state(self):
        """customs.landed.cost.line.write() is also guarded in approved state."""
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        lc.with_context(bypass_lock=True).write({'customs_state': 'approved'})
        with self.assertRaises(UserError):
            line.write({'product_cost': 999.0})
