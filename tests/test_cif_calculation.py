from odoo.tests import tagged
from .common import AdvanceLandedCostTestCommon


@tagged('post_install', '-at_install')
class TestCifCalculation(AdvanceLandedCostTestCommon):

    def test_cif_value_is_sum_of_inputs(self):
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({'freight': 100.0, 'insurance': 50.0})
        self.assertAlmostEqual(line.cif_value, 1150.0, places=2)

    def test_tax_base_without_uplift(self):
        self.company.customs_cif_uplift = False
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        self.assertAlmostEqual(line.tax_base, 1000.0, places=2)

    def test_tax_base_with_uplift(self):
        self.company.customs_cif_uplift = True
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        self.assertAlmostEqual(line.tax_base, 1100.0, places=2)
        self.company.customs_cif_uplift = False

    def test_manual_override_uses_cif_override(self):
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({'manual_override': True, 'cif_override': 1500.0})
        self.assertAlmostEqual(line.cif_value, 1500.0, places=2)

    def test_manual_override_ignores_product_cost_change(self):
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({'manual_override': True, 'cif_override': 1500.0})
        line.write({'product_cost': 999.0})
        self.assertAlmostEqual(line.cif_value, 1500.0, places=2,
                               msg="CIF should remain at override value when manual_override=True")

    def test_clearing_manual_override_restores_compute(self):
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0,
                               freight=100.0, insurance=50.0)
        line.write({'manual_override': True, 'cif_override': 9999.0})
        line.write({'manual_override': False})
        self.assertAlmostEqual(line.cif_value, 1150.0, places=2)

    def test_split_by_current_cost(self):
        lc = self._make_lc(method='by_current_cost')
        line_a = self._make_line(lc, self.product_a, cost=300.0)
        line_b = self._make_line(lc, self.product_b, cost=700.0)
        weights = lc._compute_split_weights(
            line_a | line_b, 'by_current_cost'
        )
        total = sum(weights.values())
        self.assertAlmostEqual(weights[line_a.id] / total, 0.3, places=5)
        self.assertAlmostEqual(weights[line_b.id] / total, 0.7, places=5)

    def test_split_by_quantity(self):
        lc = self._make_lc(method='by_quantity')
        line_a = self._make_line(lc, self.product_a, qty=1.0, cost=300.0)
        line_b = self._make_line(lc, self.product_b, qty=3.0, cost=700.0)
        weights = lc._compute_split_weights(
            line_a | line_b, 'by_quantity'
        )
        total = sum(weights.values())
        self.assertAlmostEqual(weights[line_a.id] / total, 0.25, places=5)
        self.assertAlmostEqual(weights[line_b.id] / total, 0.75, places=5)

    def test_split_by_weight(self):
        lc = self._make_lc(method='by_weight')
        line_a = self._make_line(lc, self.product_a, qty=1.0, cost=500.0)
        # product_a.weight=10, product_b.weight=5
        line_b = self._make_line(lc, self.product_b, qty=2.0, cost=500.0)
        weights = lc._compute_split_weights(
            line_a | line_b, 'by_weight'
        )
        # a: 10*1=10, b: 5*2=10 => equal share
        total = sum(weights.values())
        self.assertAlmostEqual(weights[line_a.id] / total, 0.5, places=5)
        self.assertAlmostEqual(weights[line_b.id] / total, 0.5, places=5)

    def test_split_equal(self):
        lc = self._make_lc(method='equal')
        line_a = self._make_line(lc, self.product_a, qty=1.0, cost=100.0)
        line_b = self._make_line(lc, self.product_b, qty=10.0, cost=9000.0)
        weights = lc._compute_split_weights(
            line_a | line_b, 'equal'
        )
        self.assertEqual(weights[line_a.id], weights[line_b.id])

    def test_distribute_cif_via_shipping_bill(self):
        lc = self._make_lc(method='by_current_cost')
        line_a = self._make_line(lc, self.product_a, cost=300.0)
        line_b = self._make_line(lc, self.product_b, cost=700.0)
        bill = self._make_shipping_bill(lc, 100.0)
        if not bill:
            self.skipTest("No purchase journal / expense account available")
        lc._distribute_cif()
        self.assertAlmostEqual(line_a.freight, 30.0, places=2)
        self.assertAlmostEqual(line_b.freight, 70.0, places=2)

    def test_recalculate_wizard_clears_override_and_logs(self):
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({'manual_override': True, 'cif_override': 1500.0})
        self.assertTrue(line.manual_override)

        wizard = self.env['customs.recalculate.wizard'].create({
            'landed_cost_id': lc.id,
            'reason': 'Test recalculation',
            'reset_overrides': True,
        })
        wizard.action_recalculate()

        self.assertFalse(line.manual_override)
        log = self.env['customs.cif.override.log'].search([
            ('landed_cost_id', '=', lc.id),
            ('line_id', '=', line.id),
        ])
        self.assertTrue(log, "CIF override log entry should have been created")
        self.assertAlmostEqual(log.old_cif, 1500.0, places=2)
