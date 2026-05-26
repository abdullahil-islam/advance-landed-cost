# Advance Landed Cost — User Guide

**Module:** `advance_landed_cost`  
**Compatible with:** Odoo 19 Enterprise  
**Extends:** `stock_landed_costs` (standard Odoo module)

---

## Overview

The **Advance Landed Cost** module extends Odoo's built-in landed cost functionality with a complete customs duties workflow for import-heavy businesses. It adds HS code management, a country/region-aware duty rate table, a CIF calculation engine with five split methods, per-levy breakdowns (Duty, VAT, CESS, SSCL), one-click bill generation, custom journal entries, and a four-stage approval workflow — all with full audit trails and multi-company support.

---

## Implemented Features

### 1. HS Code Management
- Create and manage Harmonised System (HS) codes at company or global level
- Assign HS codes directly to product templates, or inherit from the product category
- Toggle `Inherit HS from Category` per product to switch between direct assignment and category fallback
- HS codes are validated at the "Confirm" step — a landed cost with any product missing an HS code cannot be confirmed

### 2. Customs Duty Rate Table
- Configure rates per HS code with three scope levels (lookup priority: Country → Region → Global)
- **Country-specific rates** — apply only when the origin country exactly matches
- **Region rates** — apply to all countries in a named trade region (e.g. EU, ASEAN)
- **Global default rates** — fallback when no country or region match is found
- Company-specific rates take priority over global rates at the same scope level
- Date ranges (`Valid From` / `Valid To`) control when a rate is active; overlapping ranges for the same HS code + scope are blocked by a validation constraint
- Four levy rates per record: `Duty Rate (%)`, `VAT Rate (%)`, `CESS Rate (%)`, `SSCL Rate (%)`

### 3. Company Settings (Settings → Inventory → Customs Duties)
| Setting | Default | Description |
|---|---|---|
| Enable VAT | ✓ | Include VAT in customs duty calculations |
| Enable CESS | ✓ | Include CESS in calculations |
| Enable SSCL | ✗ | Include SSCL in calculations |
| Apply 10% CIF Uplift | ✗ | Multiply CIF × 1.10 as the base for VAT / CESS / SSCL |
| Allow Manual Duty Override | ✓ | Let Customs Managers override computed amounts |
| Customs Journal | — | Journal for customs duty journal entries at validation |
| Customs Duty Payable | — | Account credited for Duty / CESS / SSCL |
| VAT Receivable | — | Account debited for input VAT on imports |
| VAT Payable | — | Account credited for VAT payable to customs |
| Freight Payable | — | Account credited for freight charges |
| Insurance Payable | — | Account credited for insurance charges |

### 4. Landed Cost Extension
Every `stock.landed.cost` record gains:
- **Customs Reference** — auto-assigned sequence number (`ALC/YYYY/NNNNN`)
- **Customs Status** — separate state machine: Draft → Confirmed → Approved → Done
- **Country of Origin** — used for duty rate lookup across all lines
- **CIF Split Method** — controls how freight and insurance are distributed

### 5. CIF Calculation Engine
- **CIF Calculation tab** — add product lines with quantity and product cost; freight and insurance are distributed automatically
- **Five split methods:**
  - *By Current Cost* — proportional to each line's product cost
  - *By Quantity* — proportional to quantity
  - *By Weight* — proportional to `product weight × quantity`
  - *By Volume* — proportional to `product volume × quantity`
  - *Equal* — equal share per line
- Freight is sourced from the sum of linked **Shipping Bills** (`amount_untaxed`); insurance from **Insurance Bills**
- Click **Recalculate CIF & Duties** to redistribute after adding or changing bills
- The `Recalculate` wizard requires a mandatory reason; optionally resets manual overrides and logs each reset to the CIF Override Audit Log

### 6. Duty Calculation Engine
- Automatically computed from the rate table once CIF is set
- `duty_amount = CIF × duty_rate / 100`
- `vat_amount = tax_base × vat_rate / 100` (tax_base = CIF × 1.10 if uplift enabled)
- CESS and SSCL follow the same formula on `tax_base`, gated by company toggles
- `total_taxes = duty + vat + cess + sscl`
- Totals (Duty, VAT, CESS, SSCL, Grand Total) shown on the **Duty Calculations** tab and in the **Totals** summary group

### 7. Manual Override
Customs Managers can override CIF or duty values on individual lines:

**CIF Override** — on any non-locked line, enable `Manual Override`, then enter a value in the `Manual CIF` column. The computed CIF/duty for that line are replaced by the override value until the override is cleared.

**Duty Override Wizard** — click **Manual Duty Override** (Duty Calculations tab) to open a per-line wizard showing current vs. new Duty/VAT/CESS/SSCL values. A mandatory reason is required. The change is logged to the Duty Override Audit Log.

Both overrides are prevented when the landed cost is in **Approved** or **Done** state.

### 8. Bill Generation
Three header buttons generate pre-filled vendor bills:

| Button | Bill Type | Pre-filled Lines |
|---|---|---|
| Generate Customs Bill | Customs | Customs Duty, Import VAT, CESS, SSCL |
| Generate Shipping Bill | Shipping | Freight / Shipping |
| Generate Insurance Bill | Insurance | Insurance |

- Accounts on bill lines are pulled from the company settings; lines with zero amount are skipped
- If the landed cost is in a foreign currency, the bill is created in that currency and the original amount is stored in `Amount (Foreign Currency)` for reference
- Stat buttons in the form header show the count of each bill type; clicking navigates to the filtered bill list
- The **Bills Status** badge (All Bills Paid / Partially Paid / Bills Unpaid / No Bills) provides an at-a-glance payment summary

### 9. Approval Workflow

```
Draft  →[Customs User]  Confirmed  →[Finance Manager]  Approved  →[Finance Manager]  Done
         Confirm                   Approve                        Validate & Post
```

- **Confirm** (Customs User): validates that every line has an HS code; posts a chatter warning for lines with no applicable duty rate
- **Approve** (Finance Manager): locks the record — no further edits are allowed
- **Validate & Post** (Finance Manager): runs Odoo's standard inventory valuation, then posts the customs duty journal entries, then sets state = Done
- **Reset to Draft** (Finance Manager): available from Confirmed or Approved; not available from Done

### 10. Customs Journal Entries
At validation, a single balanced journal entry is created:

| Side | Account | Amount |
|---|---|---|
| Debit | Inventory Valuation (per product category) | Duty + CESS + SSCL + Freight + Insurance |
| Debit | VAT Receivable | VAT |
| Credit | Customs Duty Payable | Duty + CESS + SSCL |
| Credit | VAT Payable | VAT |
| Credit | Freight Payable | Freight |
| Credit | Insurance Payable | Insurance |

- The entry is immediately posted (confirmed) via `action_post()`
- If accounts are not configured or the entry would be unbalanced, a chatter warning is posted and the entry is skipped — the validation still completes
- Posted entries appear in the **Journal Entries** tab (visible to Finance Managers)

### 11. Audit Trails
Two append-only audit logs (visible in tabs to Customs Managers):

- **CIF Override Log** — records every CIF manual override and every recalculation that clears overrides: old CIF, new CIF, reason, user, timestamp
- **Duty Override Log** — records every duty manual override: old duty, new duty, reason, user, timestamp

Log entries cannot be modified or deleted (ACL: `perm_write=0`, `perm_unlink=0`).

### 12. Multi-Company Support
- All new models carry `company_id`; record rules filter to "own company OR global (`company_id = False`)"
- Rate lookup applies `ORDER BY company_id DESC NULLS LAST` — company-specific rates are always preferred over global rates at the same scope
- Company settings (toggles, accounts, journal) are scoped per company via `related=` fields
- Demo HS codes, regions, levies, and duty rates ship as global records (`company_id = False`) visible to all companies

---

## User Roles

| Role | Group | Capabilities |
|---|---|---|
| Customs User | `group_customs_user` | Create / edit landed costs and lines; confirm; view all tabs and audit logs |
| Customs Manager | `group_customs_manager` | Everything above + generate bills, manual CIF/duty overrides, recalculate wizard, delete lines |
| Finance Manager | `group_finance_manager` | Everything above + approve, validate & post, reset to draft, view journal entries |

---

## Setup Checklist

1. **Assign roles** — Go to Settings → Users and assign the appropriate Customs / Finance group to each user
2. **Create HS codes** — Navigate to Inventory → Customs → HS Codes; create codes for all imported products (or assign existing codes to product categories)
3. **Assign HS codes to products** — On each product template, set the HS Code or enable "Inherit from Category"
4. **Configure duty rates** — Inventory → Customs → Duty Rates; create rates for each HS code / country / region combination
5. **Configure company settings** — Settings → Inventory → Customs Duties; enable/disable levies; set accounting accounts and journal
6. **Set product category accounts** — Each product category used in imports needs a `Stock Valuation Account` set (Inventory → Configuration → Product Categories) for journal entries to balance correctly

---

## Typical Workflow

1. **Create a landed cost** (Inventory → Operations → Landed Costs)
   - Set Country of Origin and CIF Split Method
   - Add lines under the CIF Calculation tab: product, quantity, product cost

2. **Link bills**
   - Click Generate Shipping Bill and/or Generate Insurance Bill
   - Enter the freight and insurance amounts in the generated bills; no need to post them yet

3. **Distribute CIF**
   - Click **Recalculate CIF & Duties** to distribute freight/insurance across lines
   - The duty amounts recalculate automatically

4. **Review and override (optional)**
   - Switch to the Duty Calculations tab to review per-line duties
   - Use Manual Duty Override if any computed value needs adjusting

5. **Confirm** — Customs User clicks Confirm; any missing HS codes raise an error

6. **Approve** — Finance Manager clicks Approve; the record is locked for editing

7. **Generate Customs Bill** — Finance Manager (or Customs Manager) generates and posts the customs duty bill

8. **Validate & Post** — Finance Manager clicks Validate & Post:
   - Odoo's standard inventory valuation runs
   - Customs duty journal entries are posted
   - State becomes Done; all editing is permanently locked

---

## FAQ

**Why are duty amounts showing as zero?**  
Either (a) the product's HS code has no applicable rate for the selected Country of Origin, or (b) the Country of Origin field is empty on the landed cost. Check Inventory → Customs → Duty Rates and ensure a rate covers the relevant HS code and country/date.

**The "Validate & Post" button is greyed out.**  
The record must be in **Approved** state. Click Confirm first (Customs User), then Approve (Finance Manager).

**Journal entries were skipped after validation.**  
This is a non-blocking warning. Check the chatter for details — typically it means the Customs Duty Payable account is not set in Settings, or product categories are missing a Stock Valuation Account.

**Can I undo a Done record?**  
No. Done is a terminal state. Contact your system administrator if a correction is required; the usual approach is to create a correcting entry or a new landed cost.

**The "Manual Duty Override" button is not visible.**  
The button requires **Customs Manager** access. Contact your administrator to assign the correct group.

**How do I add a new trade region?**  
Inventory → Customs → Trade Regions → New. Add member countries via the Countries tab. Any duty rate linked to this region will then apply to imports from any of those countries.
