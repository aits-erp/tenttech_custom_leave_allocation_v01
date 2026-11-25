# Copyright (c) 2026, Sukku and contributors
# For license information, please see license.txt

# import frappe

"""WIP Breakup (Script Report).

How ERPNext records WIP (verified in v15.78 source):

* ``Material Transfer for Manufacture`` Stock Entry (linked via ``work_order``) moves raw
  material from the source warehouse into the Work Order's WIP warehouse. A return of unused
  material is the same purpose with ``is_return = 1``.
* ``Manufacture`` Stock Entry consumes raw materials (rows with a source warehouse that are
  neither ``is_finished_item`` nor ``is_scrap_item``) from the WIP warehouse and receives the
  finished good (``is_finished_item = 1``). ``Material Consumption for Manufacture`` consumes
  without producing.
* Work Orders with ``skip_transfer = 1`` never use the WIP warehouse: material is consumed
  straight from the source warehouse, so their WIP is always nil.

Per Work Order and material, everything is derived from submitted Stock Entry Detail rows
dated up to To Date (drafts and cancelled entries are excluded):

    transferred = non-return transfers - return transfers      (qty and ``amount``)
    consumed    = actual consumption rows                      (qty and ``amount``)
    remaining   = max(transferred qty - consumed qty, 0)
    WIP value   = remaining qty x transfer rate (net transferred value / net transferred qty)

The remaining value is deliberately not "transferred value - consumed value": ERPNext values
consumption at the *WIP warehouse's* moving average, which blends all Work Orders sharing the
warehouse. Valuing the remaining quantity at the Work Order's own transfer rate attributes WIP
to the correct Work Order, and equals the WIP warehouse ledger value when one Work Order uses it.
No BOM/planned costs are used.

Work Orders listed: submitted Work Orders of the company that had a transfer/manufacture/
consumption entry between From Date and To Date, plus Work Orders currently "In Process".
Selecting a Work Order always shows it. All quantities and values are measured as of To Date;
Work Order Status is the current status.

The Total row is added by the framework (``add_total_row = 1`` in the report definition),
so this script returns plain data rows only.
"""

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import flt, getdate, nowdate

VIEW_SUMMARY = "Work Order Summary"
VIEW_MATERIAL = "Material-wise Breakup"
PURPOSES = ("Material Transfer for Manufacture", "Manufacture", "Material Consumption for Manufacture")
CONSUME_PURPOSES = ("Manufacture", "Material Consumption for Manufacture")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	summary, materials = get_wip_data(filters)

	if filters.view == VIEW_MATERIAL:
		columns, data = get_material_columns(), materials
	else:
		columns, data = get_summary_columns(), summary

	return columns, data, None, get_chart(summary), get_report_summary(summary)


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	if not filters.get("from_date"):
		frappe.throw(_("From Date is mandatory"))
	if not filters.get("to_date"):
		filters.to_date = nowdate()
	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be greater than To Date"))
	filters.view = filters.get("view") or VIEW_SUMMARY
	if filters.view not in (VIEW_SUMMARY, VIEW_MATERIAL):
		frappe.throw(_("Invalid View: {0}").format(filters.view))


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def get_work_orders(filters):
	cond, values = "", {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"purposes": PURPOSES,
	}
	if filters.get("work_order"):
		cond += " AND `tabWork Order`.name = %(work_order)s"
		values["work_order"] = filters.work_order
	else:
		# bounded candidate set: activity inside the range, or still in process
		cond += """ AND (`tabWork Order`.status = 'In Process' OR `tabWork Order`.name IN (
			SELECT se.work_order FROM `tabStock Entry` se
			WHERE se.docstatus = 1 AND se.purpose IN %(purposes)s
				AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND IFNULL(se.work_order, '') != ''))"""
	if filters.get("production_item"):
		cond += " AND `tabWork Order`.production_item = %(production_item)s"
		values["production_item"] = filters.production_item
	if filters.get("wip_warehouse"):
		cond += " AND `tabWork Order`.wip_warehouse = %(wip_warehouse)s"
		values["wip_warehouse"] = filters.wip_warehouse
	if filters.get("status"):
		cond += " AND `tabWork Order`.status = %(status)s"
		values["status"] = filters.status
	if filters.get("item_group"):
		lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"]) or (0, 0)
		cond += """ AND item.item_group IN (
			SELECT name FROM `tabItem Group` WHERE lft >= %(ig_lft)s AND rgt <= %(ig_rgt)s)"""
		values.update(ig_lft=lft, ig_rgt=rgt)
	cond += get_match_cond("Work Order")  # user permissions (company etc.)

	return frappe.db.sql(
		f"""
		SELECT `tabWork Order`.name AS work_order, `tabWork Order`.status AS status,
			`tabWork Order`.production_item AS production_item,
			`tabWork Order`.item_name AS item_name, item.item_group AS item_group,
			`tabWork Order`.qty AS qty, `tabWork Order`.wip_warehouse AS wip_warehouse,
			`tabWork Order`.skip_transfer AS skip_transfer
		FROM `tabWork Order`
		LEFT JOIN `tabItem` item ON item.name = `tabWork Order`.production_item
		WHERE `tabWork Order`.docstatus = 1 AND `tabWork Order`.company = %(company)s {cond}
		ORDER BY `tabWork Order`.creation, `tabWork Order`.name
		""",
		values,
		as_dict=True,
	)


def get_movements(work_orders, to_date):
	return frappe.db.sql(
		"""
		SELECT se.work_order, sed.item_code,
			SUM(CASE WHEN se.purpose = 'Material Transfer for Manufacture' AND se.is_return = 0
				THEN sed.transfer_qty ELSE 0 END) AS tr_qty,
			SUM(CASE WHEN se.purpose = 'Material Transfer for Manufacture' AND se.is_return = 0
				THEN sed.amount ELSE 0 END) AS tr_val,
			SUM(CASE WHEN se.purpose = 'Material Transfer for Manufacture' AND se.is_return = 1
				THEN sed.transfer_qty ELSE 0 END) AS ret_qty,
			SUM(CASE WHEN se.purpose = 'Material Transfer for Manufacture' AND se.is_return = 1
				THEN sed.amount ELSE 0 END) AS ret_val,
			SUM(CASE WHEN se.purpose IN %(consume)s AND sed.is_finished_item = 0 AND sed.is_scrap_item = 0
				AND IFNULL(sed.s_warehouse, '') != '' THEN sed.transfer_qty ELSE 0 END) AS con_qty,
			SUM(CASE WHEN se.purpose IN %(consume)s AND sed.is_finished_item = 0 AND sed.is_scrap_item = 0
				AND IFNULL(sed.s_warehouse, '') != '' THEN sed.amount ELSE 0 END) AS con_val,
			SUM(CASE WHEN se.purpose = 'Manufacture' AND sed.is_finished_item = 1
				THEN sed.transfer_qty ELSE 0 END) AS fg_qty,
			SUM(CASE WHEN se.purpose = 'Manufacture' AND sed.is_finished_item = 1
				THEN sed.amount ELSE 0 END) AS fg_val
		FROM `tabStock Entry` se
		INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
		WHERE se.docstatus = 1 AND se.purpose IN %(purposes)s
			AND se.work_order IN %(wos)s AND se.posting_date <= %(to_date)s
		GROUP BY se.work_order, sed.item_code
		""",
		{
			"wos": tuple(w.work_order for w in work_orders),
			"to_date": to_date,
			"purposes": PURPOSES,
			"consume": CONSUME_PURPOSES,
		},
		as_dict=True,
	)


def get_wip_data(filters):
	work_orders = get_work_orders(filters)
	if not work_orders:
		return [], []

	names = tuple(w.work_order for w in work_orders)
	required = frappe.db.sql(
		"""SELECT parent, item_code, required_qty FROM `tabWork Order Item`
		WHERE parent IN %(wos)s AND parenttype = 'Work Order'""",
		{"wos": names},
		as_dict=True,
	)
	moves = get_movements(work_orders, filters.to_date)

	item_codes = {r.item_code for r in required} | {m.item_code for m in moves}
	item_info = {
		i.name: i
		for i in frappe.get_all(
			"Item", filters={"name": ["in", list(item_codes)]}, fields=["name", "item_name", "item_group"]
		)
	}

	mat = {}  # (wo, item) -> row
	for r in required:
		mat[(r.parent, r.item_code)] = frappe._dict(required_qty=flt(r.required_qty))
	fg = {}
	for m in moves:
		if flt(m.fg_qty) or flt(m.fg_val):
			f = fg.setdefault(m.work_order, [0.0, 0.0])
			f[0] += flt(m.fg_qty)
			f[1] += flt(m.fg_val)
		if any(flt(m[k]) for k in ("tr_qty", "ret_qty", "con_qty")):
			row = mat.setdefault((m.work_order, m.item_code), frappe._dict(required_qty=0.0))
			row.update(
				tr_qty=flt(m.tr_qty) - flt(m.ret_qty),
				tr_val=flt(m.tr_val) - flt(m.ret_val),
				con_qty=flt(m.con_qty),
				con_val=flt(m.con_val),
			)

	by_wo = {w.work_order: w for w in work_orders}
	material_rows, summary = [], []
	for w in work_orders:
		w.update(
			required_qty=0.0,
			transferred_qty=0.0,
			consumed_qty=0.0,
			transferred_value=0.0,
			consumption_value=0.0,
			wip_value=0.0,
			fg_value=0.0,
		)

	for (wo, item), r in sorted(mat.items()):
		w = by_wo[wo]
		tr_qty, tr_val = flt(r.get("tr_qty")), flt(r.get("tr_val"))
		con_qty, con_val = flt(r.get("con_qty")), flt(r.get("con_val"))
		rate = tr_val / tr_qty if tr_qty else (con_val / con_qty if con_qty else 0.0)
		# skip_transfer Work Orders consume straight from stock: nothing is ever in WIP
		remaining = 0.0 if w.skip_transfer else max(tr_qty - con_qty, 0.0)
		info = item_info.get(item) or frappe._dict()
		row = frappe._dict(
			work_order=wo,
			item_code=item,
			item_name=info.get("item_name"),
			item_group=info.get("item_group"),
			required_qty=flt(r.required_qty),
			transferred_qty=tr_qty,
			consumed_qty=con_qty,
			remaining_qty=remaining,
			valuation_rate=rate,
			transferred_value=tr_val,
			consumption_value=con_val,
			material_value=remaining * rate,
			wip_warehouse=w.wip_warehouse,
		)
		material_rows.append(row)
		w.required_qty += row.required_qty
		w.transferred_qty += tr_qty
		w.consumed_qty += con_qty
		w.transferred_value += tr_val
		w.consumption_value += con_val
		w.wip_value += row.material_value

	for w in work_orders:
		produced, fg_val = fg.get(w.work_order, [0.0, 0.0])
		w.produced_qty = produced
		w.fg_value = fg_val
		w.pending_qty = max(flt(w.qty) - produced, 0.0)
		w.progress = min(produced / flt(w.qty) * 100, 100.0) if flt(w.qty) else 0.0
		summary.append(w)

	return summary, material_rows


# --------------------------------------------------------------------------- #
# Columns
# --------------------------------------------------------------------------- #
def _col(label, fieldname, fieldtype="Data", width=110, options=None):
	c = {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
	if options:
		c["options"] = options
	return c


def get_summary_columns():
	return [
		_col("Work Order", "work_order", "Link", 150, "Work Order"),
		_col("Work Order Status", "status", "Data", 110),
		_col("Production Item", "production_item", "Link", 140, "Item"),
		_col("Item Name", "item_name", "Data", 160),
		_col("Item Group", "item_group", "Link", 120, "Item Group"),
		_col("Work Order Qty", "qty", "Float"),
		_col("Produced Qty", "produced_qty", "Float"),
		_col("Pending Production Qty", "pending_qty", "Float", 120),
		_col("Required Raw Material Qty", "required_qty", "Float", 130),
		_col("Transferred Material Qty", "transferred_qty", "Float", 130),
		_col("Actual Consumed Qty", "consumed_qty", "Float", 120),
		_col("WIP Warehouse", "wip_warehouse", "Link", 160, "Warehouse"),
		_col("Material Transferred Value", "transferred_value", "Currency", 130),
		_col("Material Consumption Value", "consumption_value", "Currency", 130),
		_col("Finished Goods Value", "fg_value", "Currency", 130),
		_col("WIP Value", "wip_value", "Currency", 120),
		_col("Production Progress %", "progress", "Percent", 110),
	]


def get_material_columns():
	return [
		_col("Work Order", "work_order", "Link", 150, "Work Order"),
		_col("Material Item", "item_code", "Link", 140, "Item"),
		_col("Item Name", "item_name", "Data", 170),
		_col("Item Group", "item_group", "Link", 120, "Item Group"),
		_col("Required Qty", "required_qty", "Float"),
		_col("Transferred Qty", "transferred_qty", "Float"),
		_col("Consumed Qty", "consumed_qty", "Float"),
		_col("Remaining Qty (in WIP)", "remaining_qty", "Float", 130),
		_col("Valuation Rate", "valuation_rate", "Currency"),
		_col("Transferred Value", "transferred_value", "Currency", 120),
		_col("Consumption Value", "consumption_value", "Currency", 120),
		_col("Material Value (in WIP)", "material_value", "Currency", 130),
		_col("WIP Warehouse", "wip_warehouse", "Link", 160, "Warehouse"),
	]


# --------------------------------------------------------------------------- #
# KPIs and charts
# --------------------------------------------------------------------------- #
def get_report_summary(summary):
	return [
		{
			"value": sum(flt(w.wip_value) for w in summary),
			"label": _("Total WIP Value"),
			"datatype": "Currency",
			"indicator": "Orange",
		},
		{"value": len(summary), "label": _("Total Work Orders"), "datatype": "Int", "indicator": "Blue"},
		{
			"value": sum(flt(w.pending_qty) for w in summary),
			"label": _("Total Pending Production Qty"),
			"datatype": "Float",
			"indicator": "Red",
		},
		{
			"value": sum(flt(w.consumption_value) for w in summary),
			"label": _("Total Material Consumption Value"),
			"datatype": "Currency",
			"indicator": "Green",
		},
	]


def _series(summary, field, limit=15):
	top = sorted(summary, key=lambda w: flt(w[field]), reverse=True)[:limit]
	return [w.work_order for w in top], [flt(w[field]) for w in top]


def get_chart(summary):
	"""Native chart = WIP value per Work Order; the JS renders all three from ``extra``."""
	if not summary:
		return None
	labels, wip = _series(summary, "wip_value")
	return {
		"data": {"labels": labels, "datasets": [{"name": _("WIP Value"), "values": wip}]},
		"type": "bar",
		"colors": ["#e07b39"],
		"extra": {
			"wip": {"labels": labels, "values": wip},
			"pending": dict(zip(("labels", "values"), _series(summary, "pending_qty"))),
			"consumption": dict(zip(("labels", "values"), _series(summary, "consumption_value"))),
		},
	}