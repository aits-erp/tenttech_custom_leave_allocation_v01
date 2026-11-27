"""Shared, permission-aware access to the Stock Ledger.

Quantity follows ERPNext's Stock Balance report: a Stock Reconciliation without a batch (or with
serial numbers) states the new balance in ``qty_after_transaction``, so its movement is the
difference from the previous entry of the same item and warehouse, not ``actual_qty``.
"""

import frappe
from frappe.desk.reportview import get_match_cond

LEDGER = "`tabStock Ledger Entry`"


def ledger_query(company, to_date, item_code=None, item_group=None, warehouse=None):
	"""Return (sql, values): one row per live ledger entry up to ``to_date``.

	Every condition here keeps or drops a whole (item, warehouse) history or its tail, which the
	running-balance window needs. Do not add conditions that drop entries from the middle.
	"""
	values = {"company": company, "to_date": to_date}
	conditions = ""

	if item_code:
		conditions += f" AND {LEDGER}.item_code = %(item_code)s"
		values["item_code"] = item_code
	if item_group:
		values["ig_lft"], values["ig_rgt"] = _tree_range("Item Group", item_group)
		conditions += f""" AND {LEDGER}.item_code IN (
			SELECT i.name FROM `tabItem` i INNER JOIN `tabItem Group` g ON g.name = i.item_group
			WHERE g.lft >= %(ig_lft)s AND g.rgt <= %(ig_rgt)s)"""
	if warehouse:
		# a group warehouse includes all of its children
		values["wh_lft"], values["wh_rgt"] = _tree_range("Warehouse", warehouse)
		conditions += f""" AND {LEDGER}.warehouse IN (
			SELECT w.name FROM `tabWarehouse` w WHERE w.lft >= %(wh_lft)s AND w.rgt <= %(wh_rgt)s)"""

	# User Permissions (company, item, warehouse ...). Refers to the table by its real name,
	# so the table must not be aliased.
	conditions += get_match_cond("Stock Ledger Entry")

	sql = f"""
		SELECT
			{LEDGER}.item_code, {LEDGER}.warehouse, {LEDGER}.posting_date, {LEDGER}.project,
			{LEDGER}.voucher_type, {LEDGER}.voucher_no, {LEDGER}.stock_value_difference,
			{LEDGER}.qty_after_transaction, {LEDGER}.stock_value,
			CASE
				WHEN {LEDGER}.voucher_type = 'Stock Reconciliation'
					AND (IFNULL({LEDGER}.batch_no, '') = '' OR IFNULL({LEDGER}.serial_no, '') != '')
				THEN {LEDGER}.qty_after_transaction - IFNULL(LAG({LEDGER}.qty_after_transaction) OVER (
					PARTITION BY {LEDGER}.item_code, {LEDGER}.warehouse
					ORDER BY {LEDGER}.posting_datetime, {LEDGER}.creation), 0)
				ELSE {LEDGER}.actual_qty
			END AS qty,
			ROW_NUMBER() OVER (
				PARTITION BY {LEDGER}.item_code, {LEDGER}.warehouse
				ORDER BY {LEDGER}.posting_datetime DESC, {LEDGER}.creation DESC) AS recency
		FROM {LEDGER}
		WHERE {LEDGER}.is_cancelled = 0
			AND {LEDGER}.docstatus < 2
			AND {LEDGER}.company = %(company)s
			AND {LEDGER}.posting_date <= %(to_date)s
			{conditions}
	"""
	return sql, values


def _tree_range(doctype, name):
	return frappe.db.get_value(doctype, name, ["lft", "rgt"]) or (0, 0)
