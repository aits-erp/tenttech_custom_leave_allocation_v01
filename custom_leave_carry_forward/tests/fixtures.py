"""Shared helpers to build real ERPNext masters/transactions inside a test transaction."""

import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry as make_wo_stock_entry


def get_company():
	return frappe.db.get_value("Company", {"name": ["like", "%Demo%"]}) or frappe.db.get_value(
		"Company", {}, "name"
	)


def make_item_group(name):
	if frappe.db.exists("Item Group", name):
		return name
	return frappe.get_doc(
		{"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups"}
	).insert().name


def make_item(code, item_group="All Item Groups", valuation_rate=10):
	if frappe.db.exists("Item", code):
		return code
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"valuation_rate": valuation_rate,
		}
	)
	# India Compliance (if installed) makes an HSN code mandatory on Items
	if frappe.get_meta("Item").has_field("gst_hsn_code"):
		hsn = "99999999"
		if not frappe.db.exists("GST HSN Code", hsn):
			frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": hsn, "description": "Test"}).insert(
				ignore_permissions=True
			)
		item.gst_hsn_code = hsn
	return item.insert().name


def make_warehouse(company, name, parent=None, is_group=0):
	abbr = frappe.db.get_value("Company", company, "abbr")
	wh = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": name,
			"company": company,
			"is_group": is_group,
			"parent_warehouse": parent or f"All Warehouses - {abbr}",
		}
	).insert()
	return wh.name


def make_bom(company, item, components):
	bom = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": item,
			"quantity": 1,
			"company": company,
			"rm_cost_as_per": "Valuation Rate",
			"items": [{"item_code": rm, "qty": qty, "rate": 0} for rm, qty in components],
		}
	)
	bom.insert()
	bom.submit()
	return bom.name


def make_work_order(company, item, bom, qty, stores, wip, fg_wh, skip_transfer=0, multi_level=1):
	wo = frappe.new_doc("Work Order")
	wo.use_multi_level_bom = multi_level
	wo.production_item = item
	wo.bom_no = bom
	wo.qty = qty
	wo.company = company
	wo.fg_warehouse = fg_wh
	wo.wip_warehouse = wip
	wo.source_warehouse = stores
	wo.skip_transfer = skip_transfer
	wo.get_items_and_operations_from_bom()
	for row in wo.required_items:
		row.source_warehouse = stores
	wo.insert()
	wo.submit()
	return wo.name


def work_order_entry(wo, purpose, qty, posting_date, submit=True):
	se = frappe.get_doc(make_wo_stock_entry(wo, purpose, qty))
	se.posting_date = posting_date
	se.set_posting_time = 1
	se.insert()
	if submit:
		se.submit()
	return se.name
