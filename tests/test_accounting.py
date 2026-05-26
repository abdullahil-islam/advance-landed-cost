from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from .common import AdvanceLandedCostTestCommon


@tagged('post_install', '-at_install')
class TestAccounting(AdvanceLandedCostTestCommon):

    def test_state_machine_draft_to_confirmed(self):
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        self.assertEqual(lc.customs_state, 'draft')
        lc.action_confirm()
        self.assertEqual(lc.customs_state, 'confirmed')

    def test_confirm_raises_when_not_draft(self):
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        lc.action_confirm()
        with self.assertRaises(UserError):
            lc.action_confirm()

    def test_confirm_raises_without_hs_code(self):
        product_no_hs = self.env['product.product'].create({
            'name': 'No HS Code Product',
            'type': 'consu',
        })
        lc = self._make_lc()
        self._make_line(lc, product_no_hs, cost=500.0)
        with self.assertRaises(ValidationError):
            lc.action_confirm()

    def test_state_machine_confirmed_to_approved(self):
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        lc.action_confirm()
        lc.action_approve()
        self.assertEqual(lc.customs_state, 'approved')

    def test_reset_to_draft_from_confirmed(self):
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        lc.action_confirm()
        lc.action_reset_to_draft()
        self.assertEqual(lc.customs_state, 'draft')

    def test_reset_to_draft_from_done_raises(self):
        lc = self._make_lc()
        lc.with_context(bypass_lock=True).write({'customs_state': 'done'})
        with self.assertRaises(UserError):
            lc.action_reset_to_draft()

    def test_bill_linking_sets_landed_cost_id(self):
        lc = self._make_lc()
        bill = self._make_shipping_bill(lc, 100.0)
        if not bill:
            self.skipTest("No purchase journal / expense account available")
        self.assertEqual(bill.customs_landed_cost_id.id, lc.id)
        self.assertEqual(bill.customs_bill_type, 'shipping')

    def test_shipping_bill_count_reflects_linked_bills(self):
        lc = self._make_lc()
        bill = self._make_shipping_bill(lc, 100.0)
        if not bill:
            self.skipTest("No purchase journal / expense account available")
        self.assertEqual(lc.shipping_bill_count, 1)

    def test_bills_payment_state_no_bills(self):
        lc = self._make_lc()
        self.assertEqual(lc.bills_payment_state, 'no_bills')

    def test_bills_payment_state_not_paid(self):
        lc = self._make_lc()
        bill = self._make_shipping_bill(lc, 100.0)
        if not bill:
            self.skipTest("No purchase journal / expense account available")
        self.assertEqual(lc.bills_payment_state, 'not_paid')

    def test_generate_customs_bill_creates_and_returns_action(self):
        """action_generate_customs_bill creates a bill and returns an act_window."""
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        result = lc.action_generate_customs_bill()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'account.move')
        bill = self.env['account.move'].browse(result['res_id'])
        self.assertEqual(bill.customs_bill_type, 'customs')
        self.assertEqual(bill.customs_landed_cost_id.id, lc.id)

    def test_generate_customs_bill_line_amounts(self):
        """Customs bill is pre-filled with Duty + VAT + CESS lines."""
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        result = lc.action_generate_customs_bill()
        bill = self.env['account.move'].browse(result['res_id'])
        line_names = bill.invoice_line_ids.mapped('name')
        self.assertIn('Customs Duty', line_names)

    def test_journal_entries_skipped_without_accounts(self):
        """
        _create_customs_journal_entries() posts a chatter message and returns
        cleanly when no payable accounts are configured on the company.
        No error should be raised.
        """
        lc = self._make_lc()
        self._make_line(lc, self.product_a, cost=1000.0)
        # Ensure no payable accounts on company
        lc.company_id.write({
            'customs_duty_payable_account_id': False,
            'customs_vat_payable_account_id': False,
            'customs_freight_payable_account_id': False,
            'customs_insurance_payable_account_id': False,
        })
        # Should not raise — just skip and warn
        lc._create_customs_journal_entries()
        # No journal entry should have been created
        self.assertFalse(lc.customs_journal_entry_ids)

    def test_customs_reference_assigned_on_create(self):
        """A new landed cost receives an ALC/YYYY/NNNNN reference."""
        lc = self._make_lc()
        self.assertNotEqual(lc.customs_reference, 'New')
        self.assertTrue(lc.customs_reference.startswith('ALC/'))

    def test_grand_total_sum(self):
        """grand_total = product_cost + freight + insurance + all duties."""
        lc = self._make_lc()
        line = self._make_line(lc, self.product_a, cost=1000.0)
        line.write({'freight': 100.0})
        expected = (
            line.product_cost + line.freight + line.insurance
            + line.duty_amount + line.vat_amount
            + line.cess_amount + line.sscl_amount
        )
        self.assertAlmostEqual(lc.grand_total, expected, places=2)
