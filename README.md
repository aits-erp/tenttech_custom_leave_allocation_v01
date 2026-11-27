### custom_leave_carry_forward

Custom Casual Leave carry forward functionality for HRMS

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app custom_leave_carry_forward
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/custom_leave_carry_forward
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit

---

# Stock Summary With Detailed Breakup

The **View** filter selects **Category Summary** (default) or **Balance Listing**.

## Category Summary

Sections: header (company, period), Stock Summary by category, item-wise breakup per category, and
Difference (summary vs breakup).

Filters: Company (mandatory), From Date (default first of month), To Date (default today), Item,
Item Group (incl. children), Warehouse (a group warehouse includes its children).

### Set up the category mapping first

1. Open **Stock Category Mapping** (button on the report, or `/app/stock-category-mapping`).
2. Add one record per Item Group: choose Raw Material, Semi Finished Goods, Finished Goods or Packing Material.
3. Sub-groups inherit the nearest mapped parent. A sub-group's own mapping overrides it.
4. Run the report. Items still unmapped appear in an **Unmapped** row and section, and are listed above the report.

Records can also be loaded with Data Import. System Manager and Stock Manager can edit them.
A change applies to all periods, including past ones.

### What goes in each column

| Category | Inward | Outward |
|---|---|---|
| Raw Material, Packing Material | Purchase (Purchase Receipt, Purchase Invoice with Update Stock), net of returns | Consumption (Manufacture, Material Consumption for Manufacture, subcontracting) |
| Semi Finished Goods | Production (Manufacture, Subcontracting Receipt) | Consumption |
| Finished Goods | Production | Sales (Delivery Note, Sales Invoice with Update Stock), net of returns |

Everything else is shown, net, in **Other (Net)** columns, which appear only when needed:
Stock Reconciliation, **Material Issue**, Material Receipt, Repack, warehouse transfers (only with a
warehouse filter; they cancel out company-wide), and movements outside a category's own types, such as
purchased finished goods or sold raw material. So `Opening + Inward - Outward + Other = Closing`.

* Returns have their own row per item, marked *Purchase Return* or *Sales Return*. A sales return is a
  negative **Sales** figure, so it increases closing stock.
* Opening includes "Opening Stock" vouchers dated inside the period, as in ERPNext's Stock Balance.
* Values are the ledger's `stock_value_difference`, never qty x rate. Quantities are in stock UOM, and
  totals add different UOMs.
* Click an Inward / Outward / Other figure to list its vouchers. Click an item code for the Stock Ledger.
* **Download Excel (Report Format)** gives the two-level header layout. Menu > Export gives plain Excel or CSV.

### Reconciliation

* *Difference* compares each category summary with the sum of its item rows. Both come from the same
  ledger read, so this guards the report's arithmetic.
* The report also compares each item and warehouse's summed movements with the running balance stored
  in the ledger. Mismatches are listed at the end; check **Repost Item Valuation** for pending or failed entries.
* Check totals against ERPNext's **Stock Balance** report on your own data before relying on them.

### Limits

* Batch and serial items, subcontracting and same-company internal sales / purchases have no dedicated tests.
* The query reads the company's ledger history up to To Date. It has not been benchmarked on large data.
* Needs MariaDB 10.2 or later (window functions).

## Balance Listing

Extra filters: Stock UOM, Project, Group By (Item and Warehouse / Item / Warehouse / Item Group),
Include Zero Stock.

* Source: `Stock Ledger Entry` (`is_cancelled = 0`), never the current Bin, so any historical date works.
* Opening = entries before From Date; Inward / Outward = entries inside the period with qty (value) >= 0 / < 0;
  Closing = everything up to To Date. Value uses `stock_value_difference` (what ERPNext actually posted), not qty x rate.
  Valuation Rate = closing value / closing qty.
* Without From Date the Opening/Inward/Outward columns are hidden and only the balance as of To Date is shown.
* Reconciled in tests against ERPNext's standard **Stock Balance** report (opening, in, out, closing, qty and value).
  Only difference: vouchers flagged "Opening Stock" dated *inside* the period count as inward here.
* KPI cards, total row (weighted rate), bar chart (top 15 by value), item/warehouse links, and a "View Ledger" link
  that opens the standard Stock Ledger for that item/warehouse and period. Excel/CSV via the report menu.
* Batch / serial numbers are not broken out (v15 stores them in Serial and Batch Bundles); inventory dimensions are not included.

## Tests

Always pass `--app`; without it bench also runs other apps' test setup, which writes to the site.

```bash
bench --site <development-site> run-tests --app custom_leave_carry_forward
```
