from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class AdvanceLandedCostTestCommon(common.TransactionCase):
    """
    Shared test fixtures for the advance_landed_cost module.

    Creates:
    - one global HS code  (TEST.7208.10)
    - two consumable products, both carrying that HS code
    - one Germany-specific duty rate  (5% duty / 20% VAT / 2% CESS)
    - company settings with VAT + CESS enabled, SSCL + uplift disabled
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.company.write({
            'customs_enable_vat': True,
            'customs_enable_cess': True,
            'customs_enable_sscl': False,
            'customs_cif_uplift': False,
        })

        cls.hs_code = cls.env['customs.hs.code'].create({
            'name': 'TEST.7208.10',
            'description': 'Test HS Code – Steel',
            'company_id': False,
        })

        cls.country_de = cls.env.ref('base.de')
        cls.country_fr = cls.env.ref('base.fr')

        cls.product_a = cls.env['product.product'].create({
            'name': 'Test Product A',
            'type': 'consu',
            'weight': 10.0,
            'volume': 0.5,
        })
        cls.product_a.product_tmpl_id.write({
            'hs_code_id': cls.hs_code.id,
            'inherit_hs_from_category': False,
        })

        cls.product_b = cls.env['product.product'].create({
            'name': 'Test Product B',
            'type': 'consu',
            'weight': 5.0,
            'volume': 0.25,
        })
        cls.product_b.product_tmpl_id.write({
            'hs_code_id': cls.hs_code.id,
            'inherit_hs_from_category': False,
        })

        cls.duty_rate = cls.env['customs.duty.rate'].create({
            'hs_code_id': cls.hs_code.id,
            'country_id': cls.country_de.id,
            'date_from': '2020-01-01',
            'duty_rate': 5.0,
            'vat_rate': 20.0,
            'cess_rate': 2.0,
            'sscl_rate': 1.5,
            'company_id': False,
        })

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_lc(self, country=None, method='by_current_cost'):
        return self.env['stock.landed.cost'].create({
            'country_of_origin_id': (country or self.country_de).id,
            'cif_split_method': method,
        })

    def _make_line(self, lc, product, qty=1.0, cost=1000.0, **kw):
        vals = {
            'landed_cost_id': lc.id,
            'product_id': product.id,
            'quantity': qty,
            'product_cost': cost,
        }
        vals.update(kw)
        return self.env['customs.landed.cost.line'].create(vals)

    def _make_shipping_bill(self, lc, freight_amount):
        """Return a draft vendor bill for freight linked to the landed cost."""
        partner = self.env['res.partner'].search([], limit=1)
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id),
            ('type', '=', 'purchase'),
        ], limit=1)
        account = self.env['account.account'].search([
            ('company_id', '=', self.company.id),
            ('account_type', 'in', ['expense', 'expense_direct_cost']),
        ], limit=1)
        if not journal or not account:
            return None
        return self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'journal_id': journal.id,
            'customs_landed_cost_id': lc.id,
            'customs_bill_type': 'shipping',
            'invoice_line_ids': [(0, 0, {
                'name': 'Freight',
                'price_unit': freight_amount,
                'quantity': 1.0,
                'account_id': account.id,
            })],
        })
