# Copyright (c) 2026, Sukku and contributors
# For license information, please see license.txt

# import frappe

"""Monthly Production Quantity & Value (Script Report).

Data source (verified against ERPNext v15 source, see README):

* ``Stock Entry`` with ``purpose = 'Manufacture'`` and ``docstatus = 1`` is the
  transaction that records production against a Work Order
  (``Stock Entry.work_order``).
* Only the ``Stock Entry Detail`` rows flagged ``is_finished_item = 1`` are
  finished goods. Raw materials (``s_warehouse`` only), scrap
  (``is_scrap_item = 1``) and additional-cost rows are never counted.
* Production value = ``Stock Entry Detail.amount`` of the finished-good row
  (``basic_amount + additional_cost``), i.e. exactly what ERPNext posts to the
  stock ledger. ``valuation_rate`` is ``amount / transfer_qty``.
  Raw-material cost is already *inside* that figure (it is distributed to the
  FG rows by ``set_basic_rate``), so it is never added a second time.

The Total row is added by Frappe (Report.add_total_row = 1), not in this file.
"""

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import add_months, flt, formatdate, get_first_day, getdate

VIEW_DETAILED = "Detailed"
VIEW_MONTHLY = "Monthly Summary"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	rows = get_production_rows(filters)
	monthly = get_monthly_summary(rows, filters.from_date, filters.to_date) if rows else []

	if filters.get("view") == VIEW_MONTHLY:
		columns = get_monthly_columns()
		data = monthly
	else:
		columns = get_detail_columns()
		data = rows

	return columns, data, None, get_chart(monthly), get_report_summary(rows)


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #
def validate_filters(filters):
	if not filters.get("from_date"):
		frappe.throw(_("From Date is mandatory"))
	if not filters.get("to_date"):
		frappe.throw(_("To Date is mandatory"))

	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)

	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be greater than To Date"))

	if filters.get("view") not in (None, "", VIEW_DETAILED, VIEW_MONTHLY):
		frappe.throw(_("Invalid View: {0}").format(filters.get("view")))


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def get_production_rows(filters):
	conditions = ""
	if filters.get("work_order"):
		conditions += " AND `tabStock Entry`.work_order = %(work_order)s"

	# Respect User Permissions / company restrictions on Stock Entry.
	conditions += get_match_cond("Stock Entry")

	# posting_date range first: uses the (docstatus/purpose/posting_date) access path
	# instead of loading unrestricted production data.
	return frappe.db.sql(
		f"""
		SELECT
			`tabStock Entry`.posting_date AS posting_date,
			`tabStock Entry`.name AS stock_entry,
			`tabStock Entry`.work_order AS work_order,
			sed.item_code AS item_code,
			sed.item_name AS item_name,
			item.item_group AS item_group,
			sed.t_warehouse AS warehouse,
			sed.transfer_qty AS qty,
			sed.stock_uom AS uom,
			sed.valuation_rate AS valuation_rate,
			sed.amount AS value
		FROM `tabStock Entry`
		INNER JOIN `tabStock Entry Detail` sed ON sed.parent = `tabStock Entry`.name
		LEFT JOIN `tabItem` item ON item.name = sed.item_code
		WHERE `tabStock Entry`.docstatus = 1
			AND `tabStock Entry`.purpose = 'Manufacture'
			AND `tabStock Entry`.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND IFNULL(`tabStock Entry`.work_order, '') != ''
			AND sed.is_finished_item = 1
			AND sed.transfer_qty > 0
			{conditions}
		ORDER BY `tabStock Entry`.posting_date, `tabStock Entry`.posting_time,
			`tabStock Entry`.name, sed.idx
		""",
		filters,
		as_dict=True,
	)


def average_rate(value, qty):
	return flt(value) / flt(qty) if flt(qty) else 0.0


def get_monthly_summary(rows, from_date, to_date):
	"""One row per calendar month in range, zero-filled so trends have no gaps."""
	totals = {}
	for r in rows:
		key = getdate(r.posting_date).replace(day=1)
		bucket = totals.setdefault(key, {"qty": 0.0, "value": 0.0})
		bucket["qty"] += flt(r.qty)
		bucket["value"] += flt(r.value)

	out = []
	month = get_first_day(from_date)
	last = get_first_day(to_date)
	while month <= last:
		bucket = totals.get(month, {"qty": 0.0, "value": 0.0})
		out.append(
			{
				"month": formatdate(month, "MMM yyyy"),
				"qty": bucket["qty"],
				"value": bucket["value"],
				"avg_rate": average_rate(bucket["value"], bucket["qty"]),
			}
		)
		month = add_months(month, 1)
	return out


# --------------------------------------------------------------------------- #
# Columns
# --------------------------------------------------------------------------- #
def get_detail_columns():
	return [
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Stock Entry"),
			"fieldname": "stock_entry",
			"fieldtype": "Link",
			"options": "Stock Entry",
			"width": 160,
		},
		{
			"label": _("Work Order"),
			"fieldname": "work_order",
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 150,
		},
		{
			"label": _("Production Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 130,
		},
		{
			"label": _("Finished Goods Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{"label": _("Produced Quantity"), "fieldname": "qty", "fieldtype": "Float", "width": 120},
		{
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 70,
		},
		{"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency", "width": 120},
		{"label": _("Production Value"), "fieldname": "value", "fieldtype": "Currency", "width": 140},
	]


def get_monthly_columns():
	return [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 120},
		{"label": _("Production Quantity"), "fieldname": "qty", "fieldtype": "Float", "width": 160},
		{"label": _("Production Value"), "fieldname": "value", "fieldtype": "Currency", "width": 160},
		{"label": _("Average Production Rate"), "fieldname": "avg_rate", "fieldtype": "Currency", "width": 180},
	]


# --------------------------------------------------------------------------- #
# KPI cards and charts
# --------------------------------------------------------------------------- #
def get_report_summary(rows):
	qty = sum(flt(r.qty) for r in rows)
	value = sum(flt(r.value) for r in rows)
	work_orders = len({r.work_order for r in rows})
	return [
		{"value": qty, "label": _("Total Production Quantity"), "datatype": "Float", "indicator": "Blue"},
		{"value": value, "label": _("Total Production Value"), "datatype": "Currency", "indicator": "Green"},
		{
			"value": average_rate(value, qty),
			"label": _("Average Production Rate"),
			"datatype": "Currency",
			"indicator": "Orange",
		},
		{"value": work_orders, "label": _("Number of Work Orders"), "datatype": "Int", "indicator": "Purple"},
	]


def get_chart(monthly):
	"""Native chart = Production Quantity (bar). The JS file renders the full set of
	three charts from the extra ``monthly`` payload (the native key is ignored by Frappe)."""
	if not monthly:
		return None

	labels = [m["month"] for m in monthly]
	qty = [m["qty"] for m in monthly]
	value = [m["value"] for m in monthly]
	return {
		"data": {"labels": labels, "datasets": [{"name": _("Production Quantity"), "values": qty}]},
		"type": "bar",
		"colors": ["#4f7cff"],
		"monthly": {"labels": labels, "qty": qty, "value": value},
	}