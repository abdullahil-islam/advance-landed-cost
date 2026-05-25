# Advance Landed Cost — Odoo 19 Enterprise Implementation Plan

## Context

This module extends Odoo 19 Enterprise's standard landed cost functionality to support advanced customs duties management for import-heavy businesses. The goal is a first-class customs workflow: HS code classification, rate lookup by origin country/region, CIF calculation with 5 split methods, per-levy (duty/VAT/CESS/SSCL) computation, one-click bill generation, custom journal entries, an approval state machine, and full audit trails. API integration (Zonos) is explicitly out of scope.

---

## Feasibility Assessment

| Feature | Verdict | Note |
|---|---|---|
| User Roles & Security | ✅ Full | Standard Odoo security groups |
| HS Code Management | ✅ Full | New model + product/category extension |
| Rate Table with Date Ranges | ✅ Full | Python overlap check (portable; no PostgreSQL extension needed) |
| Rate Lookup Priority (country → region → global) | ✅ Full | Single query with ordered fallback |
| CIF Calculation (5 split methods) | ✅ Full | Mirrors Odoo's native split pattern |
| 10% CIF Uplift | ✅ Full | Computed field toggle |
| Audit Trails (CIF & Duty) | ✅ Full | Append-only log model |
| One-Click Bill Generation | ✅ Full | `account.move` creation via button |
| Multi-Currency | ✅ Full | Native `res.currency` rate lookup |
| Multi-Company | ✅ Full | Standard `company_id` + record rules |
| Approval Workflow & Record Locking | ✅ Full | `write()` guard on `customs_state` |
| Accounting Journal Entries | ✅ Full | Separate from Odoo's standard valuation entries |
| Smart Recalculation (no circular deps) | ✅ Full | Linear `@api.depends` chain — safe by design |

**Total planned effort (excl. API): ~195 hours**

---

## Technical Ground Rules

- **Module technical name:** `advance_landed_cost`
- **Base dependency:** `stock_landed_costs`, `stock_account`, `account`, `purchase`, `product`
- **Main model to inherit:** `stock.landed.cost`
- **State strategy:** Add a separate `customs_state` field (`draft/confirmed/approved/done`) rather than overriding Odoo's native `state` — avoids breaking `button_validate()` which checks `state == 'draft'`
- **`@api.depends` chain:** Strictly linear: `product_cost/freight/insurance → cif_value → duty_amount → grand_total`. Never circular.
- **Settings pattern:** Customs settings live on `res.company` (persistent, per-company); `res.config.settings` uses `related=` fields — standard Odoo pattern
- **Multi-company rate lookup:** `company_id DESC NULLS LAST` ordering returns company-specific rates before global (company_id = False) rates in a single query
- **Audit log integrity:** CIF and duty override logs have `perm_write=0`, `perm_unlink=0` in the ACL CSV — append-only at the ACL level
- **Date overlap validation:** Python `@api.constrains` (portable; no `btree_gist` PostgreSQL extension dependency)

---

## File Structure

```
advance_landed_cost/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── customs_hs_code.py
│   ├── customs_duty_region.py
│   ├── customs_duty_levy.py
│   ├── customs_duty_rate.py
│   ├── customs_landed_cost_line.py
│   ├── customs_cif_override_log.py
│   ├── customs_duty_override_log.py
│   ├── stock_landed_cost.py          # _inherit stock.landed.cost
│   ├── account_move.py               # _inherit account.move
│   ├── product_template.py           # _inherit product.template
│   ├── product_category.py           # _inherit product.category
│   └── res_config_settings.py        # _inherit res.config.settings + res.company
├── views/
│   ├── customs_hs_code_views.xml
│   ├── customs_duty_region_views.xml
│   ├── customs_duty_levy_views.xml
│   ├── customs_duty_rate_views.xml
│   ├── stock_landed_cost_views.xml   # XPath-inherits base form; adds 4 tabs
│   ├── account_move_views.xml
│   ├── product_template_views.xml
│   ├── product_category_views.xml
│   ├── res_config_settings_views.xml
│   └── menus.xml
├── security/
│   ├── advance_landed_cost_groups.xml
│   ├── advance_landed_cost_security.xml  # record rules
│   └── ir.model.access.csv
├── data/
│   ├── ir_sequence_data.xml          # ALC/YYYY/NNNNN sequence
│   └── customs_demo_data.xml
├── wizard/
│   ├── __init__.py
│   ├── customs_recalculate_wizard.py
│   └── customs_recalculate_wizard_views.xml
├── static/src/components/
│   └── bill_summary_widget/          # OWL widget: bill count + payment status badge
│       ├── bill_summary_widget.js
│       ├── bill_summary_widget.xml
│       └── bill_summary_widget.scss
└── tests/
    ├── __init__.py
    ├── common.py                     # shared setUp: HS code, country, rate, product, landed cost
    ├── test_cif_calculation.py
    ├── test_duty_calculation.py
    ├── test_multi_currency.py
    ├── test_multi_company.py
    └── test_accounting.py
```

---

## Implementation Phases

### Phase 1 — Module Scaffold & Security (6 hrs) ✅

**Goal:** Installable skeleton with correct groups, sequences, and empty ACL.

1. **`__manifest__.py`** — depends on `['stock_landed_costs', 'stock_account', 'account', 'purchase', 'product']`, lists all data/view files in correct load order (security first).

2. **`security/advance_landed_cost_groups.xml`** — Three groups under Inventory category:
   - `group_customs_user` → inherits `base.group_user`
   - `group_customs_manager` → inherits `group_customs_user`
   - `group_finance_manager` → inherits `group_customs_manager`

3. **`security/ir.model.access.csv`** — One row per model × group:
   - `customs.hs.code`: User=CRUD(no delete), Manager=CRUD, Finance=read
   - `customs.duty.rate`: User=read, Manager=CRUD
   - `customs.cif.override.log` + `customs.duty.override.log`: all roles = CR only (immutable audit logs)
   - `customs.landed.cost.line`: User=CRU, Manager=CRUD

4. **`security/advance_landed_cost_security.xml`** — Multi-company record rules for every new model using domain `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`

5. **`data/ir_sequence_data.xml`** — Sequence `advance.landed.cost` → prefix `ALC/%(year)s/`, padding 5, global (`company_id = False`)

**Verify:** Module installs; 3 groups appear in Settings → Users; sequence produces `ALC/2026/00001`.

---

### Phase 2 — HS Code Management (12 hrs)

**Models:**

`customs.hs.code` (`models/customs_hs_code.py`):
- Fields: `name` (Char, unique per company), `description` (Text), `active` (Boolean), `company_id`
- SQL constraint: `UNIQUE(name, company_id)`

`product.category` extension (`models/product_category.py`):
- Add `hs_code_id = Many2one('customs.hs.code')`

`product.template` extension (`models/product_template.py`):
- Add `hs_code_id`, `inherit_hs_from_category` (Boolean, default=True)
- Computed `effective_hs_code_id` — uses `@api.depends` on product's own code + category code; fallback chain: product → category → False
- Show only the relevant field in the view using `invisible` attrs (hide direct HS code field when inherit is checked)

**Views:** XPath-inject HS Code fields into `product.form` and `product.category.form` under the appropriate tabs.

**Verify:** HS code assigned to category; product with `inherit_hs_from_category=True` shows category's HS code in `effective_hs_code_id`.

---

### Phase 3 — Customs Rate Configuration (20 hrs)

**Models (in dependency order):**

`customs.duty.region` (`models/customs_duty_region.py`):
- Fields: `name`, `country_ids` (Many2many `res.country`), `active`, `company_id`

`customs.duty.levy` (`models/customs_duty_levy.py`):
- Fields: `name`, `levy_type` (Selection: vat/cess/sscl/custom), `rate` (Float), `include_in_vat_base` (Boolean), `active`, `company_id`

`customs.duty.rate` (`models/customs_duty_rate.py`):
- Fields: `hs_code_id` (required), `country_id`, `region_id` (mutually exclusive via `@api.constrains`), `date_from`/`date_to`, `duty_rate`, `vat_rate`, `cess_rate`, `sscl_rate`, `active`, `company_id`
- `@api.constrains('country_id', 'region_id')` — block both being set simultaneously
- `@api.constrains(...date_from, date_to...)` — Python overlap detection across same HS code + country/region combination
- `get_applicable_rate(hs_code_id, country_id, date, company_id)` — `@api.model` helper method used by the duty engine; lookup order: exact country → region → global (no country/region)

`res.company` extension (inside `models/res_config_settings.py`):
- Add: `customs_enable_vat`, `customs_enable_cess`, `customs_enable_sscl` (Boolean, defaults True/True/False)
- Add: `customs_cif_uplift` (Boolean), `customs_allow_manual_override` (Boolean)
- Add: account fields — `customs_duty_payable_account_id`, `customs_vat_receivable_account_id`, `customs_vat_payable_account_id`, `customs_freight_payable_account_id`, `customs_insurance_payable_account_id` (all Many2one `account.account`)

`res.config.settings` extension — `related=` fields pointing to `company_id.xxx`

**Verify:** Create two overlapping rates → `ValidationError`; Settings → Customs tab visible; toggle CESS off → `company.customs_enable_cess = False`.

---

### Phase 4 — Landed Cost Extension: Core Models & Views (27 hrs)

**`customs.landed.cost.line`** (`models/customs_landed_cost_line.py`):
- Parent: `landed_cost_id` (Many2one `stock.landed.cost`, cascade)
- Product: `product_id`, `hs_code_id` (computed from product/category fallback, store=True)
- CIF inputs: `product_cost`, `freight`, `insurance` (all Monetary)
- CIF outputs: `cif_value`, `tax_base` (computed, store=True) — `tax_base = cif * 1.10` if uplift enabled
- Duty outputs: `duty_amount`, `vat_amount`, `cess_amount`, `sscl_amount` (computed, store=True)
- Override: `manual_override` (Boolean), `override_reason` (Text)
- Reference: `duty_rate_id` (Many2one `customs.duty.rate`, readonly — records which rate was applied)
- Currency via `related='landed_cost_id.currency_id'`

**`stock.landed.cost` extension** (`models/stock_landed_cost.py`):
- New fields: `customs_reference` (auto from sequence), `customs_state` (Selection: draft/confirmed/approved/done), `country_of_origin_id` (Many2one `res.country`)
- Bill relationships: `shipping_bill_ids`, `customs_bill_ids`, `insurance_bill_ids` (One2many → `account.move` with domain on `customs_bill_type`)
- `cif_split_method` (Selection: by_quantity/by_weight/by_volume/by_current_cost/equal)
- Computed totals: `total_product_cost`, `total_freight`, `total_insurance`, `total_cif`, `total_duty`, `total_vat`, `total_cess`, `total_sscl`, `grand_total`
- `customs_line_ids` (One2many → `customs.landed.cost.line`)
- `write()` override: block all field changes when `customs_state in ('approved', 'done')` (allow chatter only via context flag)
- `create()` override: assign sequence to `customs_reference`
- State action methods: `action_confirm()`, `action_approve()` (Finance Manager only), `action_validate_customs()` (calls `super().button_validate()` then `_create_customs_journal_entries()`)

**`account.move` extension** (`models/account_move.py`):
- Add: `customs_landed_cost_id` (Many2one `stock.landed.cost`, index=True)
- Add: `customs_bill_type` (Selection: customs/shipping/insurance/clearing)
- Add: `customs_amount_foreign` (Monetary), `customs_foreign_currency_id` (Many2one `res.currency`)

**Override log models:**
- `customs.cif.override.log`: `landed_cost_id`, `line_id`, `old_cif`, `new_cif`, `reason` (required), `user_id` (auto), `timestamp` (auto)
- `customs.duty.override.log`: same pattern with `old_duty`, `new_duty`; `create()` checks `has_group('group_customs_manager')`

**Views** (`views/stock_landed_cost_views.xml`):
- XPath-inherit base `stock.landed.cost` form
- Add status bar showing `customs_state` + action buttons (visibility gated by state + group)
- Add 4 tabs: **CIF Calculation** (customs_line_ids tree with product_cost/freight/insurance/cif columns), **Duty Calculations** (duty/vat/cess/sscl per line), **Customs Bills** (customs_bill_ids), **Shipping Bills** (shipping_bill_ids) — plus refreshed Additional Costs tab with insurance_bill_ids
- Add linked transfers preview (read-only `picking_ids` list showing product/qty/HS code/CIF/duty)
- Add grand total summary footer

**Verify:** Landed cost form shows 4 tabs; `customs_reference` auto-fills; `write()` guard triggers on approved record.

---

### Phase 5 — CIF Calculation Engine (20 hrs)

**`_compute_cif`** on `customs.landed.cost.line`:
- `@api.depends('product_cost', 'freight', 'insurance', 'manual_override')`
- Skip computation if `manual_override = True`
- `cif_value = product_cost + freight + insurance`
- `tax_base = cif_value * 1.10 if company.customs_cif_uplift else cif_value`

**`_distribute_cif()`** on `stock.landed.cost`:
- Reads total freight from `shipping_bill_ids.amount_untaxed` sum; total insurance from `insurance_bill_ids.amount_untaxed` sum
- Calls `_compute_split_weights(lines, method)` to get per-line weight dictionary
- Writes `freight` and `insurance` to each non-overridden line proportionally

**`_compute_split_weights()`** — returns `{line.id: weight}` for each of 5 methods:
- `by_quantity`: `valuation_adjustment_line.quantity`
- `by_weight`: `product_id.weight × quantity`
- `by_volume`: `product_id.volume × quantity`
- `by_current_cost`: `product_cost`
- `equal`: `1` for each line

**Recalculate Wizard** (`wizard/customs_recalculate_wizard.py`):
- Fields: `landed_cost_id` (required), `reason` (Text, required), `reset_overrides` (Boolean, default True)
- `action_recalculate()`: for each overridden line, create `customs.cif.override.log` entry (old_cif = current cif_value); clear `manual_override`; call `_distribute_cif()`

**`@api.depends` chain is strictly linear — no circular risk:**
```
product_cost / freight / insurance
    → _compute_cif → cif_value, tax_base
    → _compute_duties → duty_amount, vat_amount, cess_amount, sscl_amount
    → _compute_totals on stock.landed.cost → grand_total
```

**Verify:** 3-line landed cost; link shipping bill; run `_distribute_cif()` for each method; check freight sums correctly; toggle override + verify that line is skipped; run wizard + check log entry created.

---

### Phase 6 — Duty Calculation Engine (17 hrs)

**`_compute_duties`** on `customs.landed.cost.line`:
- `@api.depends('cif_value', 'tax_base', 'hs_code_id', 'manual_override', 'landed_cost_id.country_of_origin_id')`
- Skip if `manual_override = True`
- Call `customs.duty.rate.get_applicable_rate(hs_code_id, country_id, today, company_id)`
- If rate found: `duty_amount = cif_value × rate.duty_rate / 100`; VAT/CESS/SSCL use `tax_base` × respective rate, gated by `company.customs_enable_*`
- If rate not found: all duty fields = 0.0; `landed_cost_id.message_post()` with warning

**Manual override flow:**
- Button on line → opens a simple wizard requiring `reason` (Text, required) + shows old/new duty fields
- Wizard `create()` checks `has_group('group_customs_manager')` — raises `UserError` if not
- Sets `line.manual_override = True`, creates `customs.duty.override.log` record
- `customs_state in ('approved', 'done')` → `write()` guard prevents override entirely

**Smart recalc triggers:** Duty recomputes automatically on:
- Bill linked/edited (via `@api.onchange` on bill relations + manual `_distribute_cif()` call)
- `country_of_origin_id` changed
- Rate table updated (no automatic trigger — user clicks "Recalculate" button which calls `_distribute_cif()`)
- Manual override toggled off (via wizard)

**Verify:** Correct duty formula; Customs User override blocked; Customs Manager override succeeds with log; approved record blocks override entirely.

---

### Phase 7 — Multi-Bill Management (20 hrs)

**Bill generation actions** (on `stock.landed.cost`):
- `action_generate_customs_bill()` → `_generate_bill('customs')`
- `action_generate_shipping_bill()` → `_generate_bill('shipping')`
- `action_generate_insurance_bill()` → `_generate_bill('insurance')`

**`_generate_bill(bill_type)`:**
- Creates `account.move` (type=`in_invoice`) with `customs_landed_cost_id = self.id` and `customs_bill_type = bill_type`
- Pre-fills line items from `_build_bill_lines(bill_type)`:
  - Customs: 4 lines — Duty (→ Customs Payable account), VAT (→ VAT Payable), CESS, SSCL
  - Shipping: 1 line — Freight (→ Freight Payable account)
  - Insurance: 1 line — Insurance (→ Insurance Payable account)
- Returns `ir.actions.act_window` to open the new bill in form view

**Multi-currency:**
- Bills in foreign currency: use `res.currency._convert(amount, target_currency, company, date=bill.invoice_date)` to convert to base currency
- Store both values: Odoo's native `amount_total` (base currency) + `customs_amount_foreign` (foreign)

**Linked bills summary widget** (OWL, `bill_summary_widget`):
- Reads `customs_bill_ids`, `shipping_bill_ids`, `insurance_bill_ids` count
- Derives payment status: all paid → "Paid", any partial/paid → "Partial", else "Unpaid"
- Displayed as a badge in the form header

**Verify:** Click each generate button → correct bill type created; bill opens pre-filled; bill count badge updates; USD bill on EUR company shows conversion.

---

### Phase 8 — Accounting Integration (18 hrs)

**`_create_customs_journal_entries()`** on `stock.landed.cost`:
- Called inside `action_validate_customs()` after `super().button_validate()`
- Creates a single `account.move` with balanced debit/credit pairs:
  - Duty: Dr Inventory Valuation / Cr `customs_duty_payable_account_id`
  - VAT: Dr `customs_vat_receivable_account_id` / Cr `customs_vat_payable_account_id`
  - Freight: Dr Inventory Valuation / Cr `customs_freight_payable_account_id`
  - Insurance: Dr Inventory Valuation / Cr `customs_insurance_payable_account_id`
- Inventory Valuation account resolved from `product.categ_id.property_stock_valuation_account_id`
- Calls `.action_post()` — Odoo validates debit = credit before posting
- These entries are separate from Odoo's standard valuation entries (no override of `_generate_moves()`)

**Approval workflow (state machine):**
```
Draft → [Customs User] Confirm → [Finance Manager] Approve → [Finance Manager] Validate → Done
```
- Button visibility: `invisible` attrs on each button keyed to `customs_state` + `groups`
- `action_approve()`: `has_group('group_finance_manager')` guard
- `action_validate_customs()`: requires `customs_state == 'approved'`
- After `Done`: `write()` guard prevents all edits

**Verify:** Validate → journal entries appear in Accounting; debit = credit on every entry; state = done; further edits blocked.

---

### Phase 9 — Multi-Company Support (8 hrs)

All new models already carry `company_id` from Phase 1–8. This phase audits and completes:

1. **Record rules** (already created in Phase 1) verified for every model
2. **Rate lookup priority within company:** `get_applicable_rate()` uses `ORDER BY company_id DESC NULLS LAST` so company-specific rates (non-null) beat global (null) in a single query
3. **Settings per company:** `res.config.settings` `related=` fields automatically scope to active company
4. **Demo data:** HS codes and duty rates use `company_id = False` so they work across all companies

**Verify:** Company A rate not visible in Company B; global rate (company_id=False) visible from both; Company A user cannot `write()` Company B's landed cost record (record rule blocks).

---

### Phase 10 — Testing & QA (24 hrs)

**`tests/common.py`** — `AdvanceLandedCostTestCommon(TransactionCase)`:
- `setUpClass`: creates HS code, country (Germany), duty rate (5% duty, 20% VAT, 2% CESS), product, company settings, a base landed cost record

**`tests/test_cif_calculation.py`:**
- `test_split_by_quantity`, `test_split_by_weight`, `test_split_by_volume`, `test_split_by_current_cost`, `test_split_equal`
- `test_cif_uplift_enabled` / `test_cif_uplift_disabled`
- `test_manual_override_skips_compute`
- `test_recalculate_wizard_clears_override_and_logs`

**`tests/test_duty_calculation.py`:**
- `test_rate_priority_country_beats_region`
- `test_rate_priority_region_beats_global`
- `test_rate_global_fallback`
- `test_rate_not_found_returns_zero`
- `test_duty_formula_correct`
- `test_vat_disabled_by_setting`
- `test_overlapping_date_constraint_raises`

**`tests/test_multi_currency.py`:**
- `test_bill_foreign_currency_conversion`
- `test_rounding_with_zero_decimal_currency`

**`tests/test_multi_company.py`:**
- `test_company_rate_not_visible_to_other_company`
- `test_global_rate_visible_to_all_companies`
- `test_cross_company_write_blocked_by_record_rule`

**`tests/test_accounting.py`:**
- `test_journal_entry_balanced` (debit = credit)
- `test_journal_entry_correct_accounts`
- `test_bill_linking_sets_landed_cost_id`
- `test_approved_state_blocks_write`
- `test_state_machine_progression`

---

## Implementation Order (Dependency Graph)

```
Phase 1: Scaffold, groups, sequences, empty ACL
    │
    ▼
Phase 2: customs.hs.code → product.category / product.template extensions
    │
    ▼
Phase 3: customs.duty.region → customs.duty.levy → customs.duty.rate
         res.company fields → res.config.settings
    │
    ▼
Phase 4: customs.landed.cost.line (needs rate + HS code)
         stock.landed.cost extension (needs line model)
         account.move extension (parallel — no dependency on line)
         Override log models (parallel — no dependency)
    │
    ▼
Phase 5: CIF engine — _distribute_cif() + recalculate wizard
    │
    ▼
Phase 6: Duty lock + manual override wizard (depends on Phase 5 CIF)
    │
    ▼
Phase 7: Bill generation + OWL bill summary widget
    │
    ▼
Phase 8: Journal entries + approval workflow view buttons
    │
    ▼
Phase 9: Multi-company audit + record rule verification
    │
    ▼
Phase 10: Full test suite
```

---

## Key Technical Decisions

| Decision | Rationale |
|---|---|
| Separate `customs_state` field (not override native `state`) | Odoo's `button_validate()` checks `state == 'draft'` — overriding would break the standard flow |
| Python `@api.constrains` for date overlap (not PostgreSQL exclusion constraint) | `btree_gist` extension not guaranteed in all Odoo 19 installs |
| Override logs: `perm_write=0`, `perm_unlink=0` in ACL | Immutable audit trail without ORM hackery |
| `res.company` holds customs settings (not `ir.config_parameter`) | Per-company scoping; `ir.config_parameter` is global |
| `_create_customs_journal_entries()` separate from `_generate_moves()` | Keeps custom duty entries traceable in GL without risk of breaking Odoo's inventory valuation |
| Bill generation opens the new bill in form view | User immediately reviews pre-filled bill instead of blind background creation |
| `manual_override=True` skips the `@api.depends` compute entirely | Simplest pattern; avoids computed-field write conflicts in Odoo ORM |
| OWL widget only for the bill summary badge | Every other UI element uses standard XML views — minimises JS maintenance surface |

---

## End-to-End Verification Checklist

1. Module installs on Odoo 19 Enterprise with no import errors or ACL warnings
2. Three roles visible in Settings → Users → Groups under Inventory
3. HS code created; assigned to product category; product inherits via `effective_hs_code_id`
4. Duty rate (Germany, steel HS code, 5%/20%/2%/1.5%) created; overlapping rate blocked
5. Landed cost created → `ALC/2026/00001` auto-assigned
6. Shipping bill linked → `_distribute_cif()` distributes freight correctly across lines
7. Duty auto-calculates: `duty = CIF × 5%`, `VAT = CIF × 20%`
8. CIF uplift toggled → `VAT = (CIF × 1.10) × 20%`
9. Manual CIF override as Customs User → blocked; as Customs Manager → succeeds with log entry
10. Click "Generate Customs Bill" → bill opens with 4 pre-filled line items
11. `action_confirm()` (Customs User) → state = Confirmed
12. `action_approve()` (Finance Manager) → state = Approved; all fields locked
13. `action_validate_customs()` → standard valuation entries + custom duty entries posted; state = Done
14. In Company B: Company A's duty rate not visible; global demo rate is visible
15. All 5 test files pass with Odoo test runner
