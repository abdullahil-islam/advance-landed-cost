from odoo.tests import tagged
from .common import AdvanceLandedCostTestCommon


@tagged('post_install', '-at_install')
class TestMultiCurrency(AdvanceLandedCostTestCommon):

    def test_line_currency_inherits_from_landed_cost(self):
        """customs.landed.cost.line.currency_id is relayed from the landed cost."""
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        self.assertEqual(line.currency_id, lc.currency_id)

    def test_generate_bill_sets_foreign_currency(self):
        """
        When the landed cost currency differs from the company base currency,
        action_generate_shipping_bill() records customs_foreign_currency_id
        on the new bill.
        """
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        eur = self.env.ref('base.EUR', raise_if_not_found=False)
        if not usd or not eur:
            self.skipTest("USD or EUR currency not available")

        # Find / activate USD
        usd.active = True

        # Locate the purchase journal for USD or any purchase journal
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id),
            ('type', '=', 'purchase'),
        ], limit=1)
        if not journal:
            self.skipTest("No purchase journal available")

        # If company currency is already USD, skip (currencies would be equal)
        if self.company.currency_id == usd:
            self.skipTest("Company already uses USD; test requires a different currency pair")

        # Create a landed cost that uses USD (non-base currency)
        lc = self.env['stock.landed.cost'].create({
            'country_of_origin_id': self.country_de.id,
            'cif_split_method': 'by_current_cost',
            'currency_id': usd.id,
        })
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({'freight': 100.0})

        result = lc.action_generate_shipping_bill()
        bill = self.env['account.move'].browse(result['res_id'])

        # Bill should carry the foreign currency info
        self.assertEqual(bill.customs_foreign_currency_id.id, usd.id)
        self.assertGreater(bill.customs_amount_foreign, 0.0)

    def test_generate_bill_no_foreign_currency_when_same(self):
        """
        When landed cost uses the same currency as the company, no foreign
        currency fields are set on the generated bill.
        """
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        result = lc.action_generate_customs_bill()
        bill = self.env['account.move'].browse(result['res_id'])
        self.assertFalse(
            bill.customs_foreign_currency_id,
            "No foreign currency should be set when currencies match"
        )

    def test_cif_override_log_currency_matches_landed_cost(self):
        """CIF override log inherits currency from the landed cost."""
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({'manual_override': True, 'cif_override': 1500.0})

        wizard = self.env['customs.recalculate.wizard'].create({
            'landed_cost_id': lc.id,
            'reason': 'Currency test',
            'reset_overrides': True,
        })
        wizard.action_recalculate()

        log = self.env['customs.cif.override.log'].search([
            ('landed_cost_id', '=', lc.id)
        ], limit=1)
        self.assertTrue(log)
        self.assertEqual(log.currency_id, lc.currency_id)
