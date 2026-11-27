# Copyright (c) 2026, Sukku and contributors
# For license information, please see license.txt

# import frappe

"""Stock Summary With Detailed Breakup (Script Report).

Source of truth is the Stock Ledger Entry (same as ERPNext's Stock Balance report),
never the current Bin, so any historical date is supported.

Per (item, warehouse) between ``from_date`` and ``to_date``:

* opening  = sum(actual_qty / stock_value_difference) of entries posted before From Date
* inward   = entries in the period with qty (value) >= 0
* outward  = entries in the period with qty (value) <  0  (shown as positive numbers)
* closing  = everything posted up to To Date = opening + inward - outward

``stock_value_difference`` is the value ERPNext itself posted, so closing value follows the
real valuation (FIFO / moving average, revaluations, landed cost) and is never qty x rate.
Cancelled ledger rows (``is_cancelled = 1``) are excluded.

Two views, chosen with the View filter: **Category Summary** (default, see ``category_summary.py``)
and **Balance Listing**, described above.

The Total row of the Balance Listing is added by Frappe itself (Report.add_total_row = 1).
The Category Summary builds its own totals and tells Frappe to skip that row.

Known difference to the standard report: vouchers flagged "Opening Stock" that fall *inside*
the period are shown as inward here (standard report moves them to opening).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from custom_leave_carry_forward.custom_leave_carry_forward.report.stock_summary_with_detailed_breakup import (
	category_summary,
)
from custom_leave_carry_forward.stock_ledger import ledger_query

CATEGORY_VIEW = "Category Summary"
LISTING_VIEW = "Balance Listing"

GROUP_ITEM_WH = "Item and Warehouse"
GROUP_ITEM = "Item"
GROUP_WH = "Warehouse"
GROUP_ITEM_GROUP = "Item Group"
GROUPS = (GROUP_ITEM_WH, GROUP_ITEM, GROUP_WH, GROUP_ITEM_GROUP)

SUM_FIELDS = ("opening_qty", "opening_val", "in_qty", "in_val", "out_qty", "out_val", "bal_qty", "bal_val")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if (filters.get("view") or CATEGORY_VIEW) != LISTING_VIEW:
		return category_summary.execute(filters)
	validate_filters(filters)

	base = get_base_rows(filters)  # one row per item + warehouse (non-zero unless requested)
	data = group_rows(base, filters.group_by)
	# No manual total row: Report.add_total_row = 1 makes Frappe append it.
	return get_columns(filters), data, None, get_chart(data, filters), get_summary(base)


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	filters.to_date = getdate(filters.get("to_date") or nowdate())
	filters.from_date = getdate(filters.from_date) if filters.get("from_date") else None
	if filters.from_date and filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be greater than To Date"))
	filters.group_by = filters.get("group_by") or GROUP_ITEM_WH
	if filters.group_by not in GROUPS:
		frappe.throw(_("Invalid Group By: {0}").format(filters.group_by))


def get_base_rows(filters):
	ledger, values = ledger_query(
		filters.company,
		filters.to_date,
		item_code=filters.get("item_code"),
		item_group=filters.get("item_group"),
		warehouse=filters.get("warehouse"),
	)
	values["from_date"] = filters.from_date or getdate("1900-01-01")

	# applied outside the ledger subquery: project would break its running balance
	conditions = ""
	if filters.get("stock_uom"):
		conditions += " AND item.stock_uom = %(stock_uom)s"
		values["stock_uom"] = filters.stock_uom
	if filters.get("project"):
		conditions += " AND sle.project = %(project)s"
		values["project"] = filters.project

	# One pass over a date-bounded slice of the ledger; conditional sums do the breakup.
	rows = frappe.db.sql(
		f"""
		SELECT sle.item_code, MAX(item.item_name) item_name, MAX(item.item_group) item_group,
			sle.warehouse, MAX(item.stock_uom) stock_uom,
			SUM(CASE WHEN sle.posting_date < %(from_date)s THEN sle.qty ELSE 0 END) AS opening_qty,
			SUM(CASE WHEN sle.posting_date < %(from_date)s THEN sle.stock_value_difference ELSE 0 END) AS opening_val,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.qty >= 0 THEN sle.qty ELSE 0 END) AS in_qty,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.stock_value_difference >= 0 THEN sle.stock_value_difference ELSE 0 END) AS in_val,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.qty < 0 THEN -sle.qty ELSE 0 END) AS out_qty,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.stock_value_difference < 0 THEN -sle.stock_value_difference ELSE 0 END) AS out_val,
			SUM(sle.qty) AS bal_qty,
			SUM(sle.stock_value_difference) AS bal_val
		FROM ({ledger}) sle
		INNER JOIN `tabItem` item ON item.name = sle.item_code
		WHERE 1 = 1 {conditions}
		GROUP BY sle.item_code, sle.warehouse
		ORDER BY sle.item_code, sle.warehouse
		""",
		values,
		as_dict=True,
	)

	out = []
	for r in rows:
		for f in SUM_FIELDS:
			r[f] = flt(r[f], 6)
		if not filters.get("include_zero_stock") and not r.bal_qty and not r.bal_val:
			continue
		r.val_rate = r.bal_val / r.bal_qty if r.bal_qty else 0.0
		out.append(r)
	return out


def group_rows(base, group_by):
	if group_by == GROUP_ITEM_WH:
		return base
	key, keep = {
		GROUP_ITEM: ("item_code", ("item_code", "item_name", "item_group", "stock_uom")),
		GROUP_WH: ("warehouse", ("warehouse",)),
		GROUP_ITEM_GROUP: ("item_group", ("item_group",)),
	}[group_by]
	grouped = {}
	for r in base:
		g = grouped.setdefault(r[key], frappe._dict({k: r[k] for k in keep}))
		for f in SUM_FIELDS:
			g[f] = flt(g.get(f)) + flt(r[f])
	rows = list(grouped.values())
	for g in rows:
		g.val_rate = g.bal_val / g.bal_qty if g.bal_qty else 0.0
	return sorted(rows, key=lambda g: str(g[key]))


def get_columns(filters):
	g = filters.group_by
	cols = []
	if g in (GROUP_ITEM_WH, GROUP_ITEM):
		cols += [
			{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
			{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		]
	if g in (GROUP_ITEM_WH, GROUP_ITEM, GROUP_ITEM_GROUP):
		cols.append(
			{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130}
		)
	if g in (GROUP_ITEM_WH, GROUP_WH):
		cols.append(
			{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 170}
		)
	if g in (GROUP_ITEM_WH, GROUP_ITEM):
		cols.append({"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 80})

	def num(label, field, ftype="Float", width=110, disable_total=0):
		col = {"label": _(label), "fieldname": field, "fieldtype": ftype, "width": width}
		if disable_total:
			col["disable_total"] = 1  # a summed rate is meaningless in the Total row
		return col

	if filters.from_date:
		cols += [
			num("Opening Qty", "opening_qty"),
			num("Opening Value", "opening_val", "Currency"),
			num("Inward Qty", "in_qty"),
			num("Inward Value", "in_val", "Currency"),
			num("Outward Qty", "out_qty"),
			num("Outward Value", "out_val", "Currency"),
		]
	cols += [
		num("Closing Qty", "bal_qty"),
		num("Closing Value", "bal_val", "Currency", 130),
		num("Valuation Rate", "val_rate", "Currency", disable_total=1),
	]
	if g in (GROUP_ITEM_WH, GROUP_ITEM, GROUP_WH):
		cols.append({"label": _("Stock Ledger"), "fieldname": "ledger_link", "fieldtype": "Data", "width": 100})
	return cols


def get_summary(rows):
	return [
		{
			"value": sum(flt(r.bal_qty) for r in rows),
			"label": _("Total Stock Quantity"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": sum(flt(r.bal_val) for r in rows),
			"label": _("Total Stock Value"),
			"datatype": "Currency",
			"indicator": "Green",
		},
		{
			"value": len({r.item_code for r in rows if r.get("item_code")}),
			"label": _("Total Items"),
			"datatype": "Int",
			"indicator": "Orange",
		},
		{
			"value": len({r.warehouse for r in rows if r.get("warehouse")}),
			"label": _("Total Warehouses"),
			"datatype": "Int",
			"indicator": "Purple",
		},
	]


def get_chart(rows, filters):
	if not rows:
		return None
	key = {
		GROUP_ITEM_WH: "item_code",
		GROUP_ITEM: "item_code",
		GROUP_WH: "warehouse",
		GROUP_ITEM_GROUP: "item_group",
	}[filters.group_by]
	top = sorted(rows, key=lambda r: flt(r.bal_val), reverse=True)
	agg = {}
	for r in top:
		agg[r[key]] = agg.get(r[key], 0) + flt(r.bal_val)
	items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:15]
	return {
		"data": {
			"labels": [k for k, _v in items],
			"datasets": [{"name": _("Closing Value"), "values": [v for _k, v in items]}],
		},
		"type": "bar",
		"colors": ["#2fa36b"],
	}