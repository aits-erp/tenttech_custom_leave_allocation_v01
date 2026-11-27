"""Category Summary view: stock summary by category, item-wise breakup and reconciliation.

Categories come from the **Stock Category Mapping** DocType (Item Group -> category; sub-groups
inherit the nearest mapped parent). Movements are classified from the voucher that posted each
Stock Ledger Entry:

=================  =============================================================================
purchase           Purchase Receipt; Purchase Invoice with Update Stock
purchase_return    the same, marked Is Return
sales              Delivery Note; Sales Invoice with Update Stock
sales_return       the same, marked Is Return
production         incoming rows of Manufacture; Subcontracting Receipt finished goods
consumption        outgoing rows of Manufacture and Material Consumption for Manufacture;
                   Subcontracting Receipt supplied materials
transfer           Material Transfer (incl. for Manufacture / Send to Subcontractor) and
                   same-company internal sales / purchases
other              everything else (Material Receipt / Issue, Repack, Stock Reconciliation ...)
=================  =============================================================================

Each category shows its own two kinds as Inward / Outward (returns netted off); every other kind
is reported, net, as "Other Movements" so that Opening + Inward - Outward + Other = Closing.
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt, formatdate, get_first_day, getdate, nowdate

from custom_leave_carry_forward.stock_ledger import ledger_query

CATEGORIES = ("Raw Material", "Semi Finished Goods", "Finished Goods", "Packing Material")
UNMAPPED = "Unmapped"

# category: (inward kinds, outward kinds, inward label, outward label)
BUCKETS = {
	"Raw Material": (("purchase", "purchase_return"), ("consumption",), "Purchase", "Consumption"),
	"Semi Finished Goods": (("production",), ("consumption",), "Production", "Consumption"),
	"Finished Goods": (("production",), ("sales", "sales_return"), "Production", "Sales"),
	"Packing Material": (("purchase", "purchase_return"), ("consumption",), "Purchase", "Consumption"),
	UNMAPPED: (
		("purchase", "purchase_return", "production"),
		("consumption", "sales", "sales_return"),
		"Inward",
		"Outward",
	),
}

VALUE_FIELDS = (
	"opening_qty", "opening_val", "in_qty", "in_val", "out_qty", "out_val",
	"other_qty", "other_val", "closing_qty", "closing_val",
)  # fmt: skip
RETURN_LABELS = {"purchase_return": "Purchase Return", "sales_return": "Sales Return"}
TRANSFER_PURPOSES = ("Material Transfer", "Material Transfer for Manufacture", "Send to Subcontractor")

# differences smaller than these are rounding, not errors
QTY_TOLERANCE = 0.001
VALUE_TOLERANCE = 0.01


def execute(filters):
	filters = validate_filters(filters)
	result = calculate(filters)
	show_other = result.show_other
	return (
		get_columns(show_other),
		build_rows(filters, result),
		get_message(result),
		None,
		get_report_summary(filters, result),
		True,  # skip_total_row: totals are part of the data
	)


def validate_filters(filters):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))
	filters.to_date = getdate(filters.get("to_date") or nowdate())
	filters.from_date = getdate(filters.get("from_date") or get_first_day(filters.to_date))
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be greater than To Date"))
	return filters


# --------------------------------------------------------------------------- data


def fetch_movements(filters):
	"""Ledger totals per item and warehouse; entries inside the period also per voucher.

	Everything before From Date collapses into one row per item and warehouse (voucher_no = '').
	"""
	ledger, values = ledger_query(
		filters.company,
		filters.to_date,
		item_code=filters.get("item_code"),
		item_group=filters.get("item_group"),
		warehouse=filters.get("warehouse"),
	)
	values["from_date"] = filters.from_date
	return frappe.db.sql(
		f"""
		SELECT item_code, warehouse,
			CASE WHEN posting_date < %(from_date)s THEN '' ELSE voucher_type END AS vtype,
			CASE WHEN posting_date < %(from_date)s THEN '' ELSE voucher_no END AS vno,
			MIN(posting_date) AS posting_date,
			SUM(qty) AS qty,
			SUM(CASE WHEN qty > 0 THEN qty ELSE 0 END) AS qty_in,
			SUM(stock_value_difference) AS value,
			SUM(CASE WHEN qty > 0 THEN stock_value_difference
				WHEN qty = 0 AND stock_value_difference > 0 THEN stock_value_difference ELSE 0 END) AS value_in,
			MAX(CASE WHEN recency = 1 THEN qty_after_transaction END) AS ledger_qty,
			MAX(CASE WHEN recency = 1 THEN stock_value END) AS ledger_val
		FROM ({ledger}) sle
		GROUP BY item_code, warehouse, vtype, vno
		""",
		values,
		as_dict=True,
	)


def get_voucher_info(movements, company):
	"""Bulk-load the voucher fields needed for classification (one query per voucher type)."""
	names = {}
	for m in movements:
		if m.vno:
			names.setdefault(m.vtype, set()).add(m.vno)

	wanted = {
		"Stock Entry": ["purpose", "is_opening"],
		"Stock Reconciliation": ["purpose"],
		"Purchase Receipt": ["is_return", "is_internal_supplier", "represents_company"],
		"Purchase Invoice": ["is_return", "is_internal_supplier", "represents_company"],
		"Delivery Note": ["is_return", "is_internal_customer", "represents_company"],
		"Sales Invoice": ["is_return", "is_internal_customer", "represents_company"],
		"Subcontracting Receipt": ["is_return"],
	}
	info = {}
	for voucher_type, voucher_names in names.items():
		if voucher_type not in wanted:
			continue
		voucher_names = list(voucher_names)
		for start in range(0, len(voucher_names), 5000):
			for row in frappe.get_all(
				voucher_type,
				filters={"name": ["in", voucher_names[start : start + 5000]]},
				fields=["name", *wanted[voucher_type]],
			):
				row.internal = bool(
					(row.get("is_internal_supplier") or row.get("is_internal_customer"))
					and row.get("represents_company") == company
				)
				info[(voucher_type, row.name)] = row
	return info


def is_opening_voucher(voucher_type, info):
	"""Same rule as ERPNext's Stock Balance: these count as opening even inside the period."""
	if not info:
		return False
	if voucher_type == "Stock Entry":
		return info.get("is_opening") == "Yes"
	return voucher_type == "Stock Reconciliation" and info.get("purpose") == "Opening Stock"


def classify(voucher_type, info, incoming):
	"""Kind of one movement. ``incoming`` is True when the entry adds stock."""
	info = info or frappe._dict()

	if voucher_type in ("Purchase Receipt", "Purchase Invoice"):
		if info.get("internal"):
			return "transfer"
		return "purchase_return" if info.get("is_return") else "purchase"
	if voucher_type in ("Delivery Note", "Sales Invoice"):
		if info.get("internal"):
			return "transfer"
		return "sales_return" if info.get("is_return") else "sales"
	if voucher_type == "Stock Entry":
		purpose = info.get("purpose")
		if purpose == "Manufacture":
			return "production" if incoming else "consumption"
		if purpose == "Material Consumption for Manufacture":
			return "consumption"
		if purpose in TRANSFER_PURPOSES:
			return "transfer"
		return "other"
	if voucher_type == "Subcontracting Receipt":
		if info.get("is_return"):
			return "consumption" if incoming else "production"
		return "production" if incoming else "consumption"
	return "other"


def split_movement(movement, info):
	"""Yield (kind, qty, value). Vouchers that both consume and produce are split by direction."""
	purpose = (info or {}).get("purpose")
	two_sided = movement.vtype == "Subcontracting Receipt" or purpose == "Manufacture"
	if not two_sided:
		yield classify(movement.vtype, info, flt(movement.qty) > 0), flt(movement.qty), flt(movement.value)
		return

	for incoming in (True, False):
		qty = flt(movement.qty_in) if incoming else flt(movement.qty) - flt(movement.qty_in)
		value = flt(movement.value_in) if incoming else flt(movement.value) - flt(movement.value_in)
		if qty or value:
			yield classify(movement.vtype, info, incoming), qty, value


def get_category_map():
	return dict(frappe.get_all("Stock Category Mapping", fields=["item_group", "category"], as_list=True))


def get_item_categories(item_codes):
	"""item_code -> category. The nearest mapped Item Group at or above the item's group wins."""
	if not item_codes:
		return {}
	mapping = get_category_map()
	groups = {g.name: g.parent_item_group for g in frappe.get_all("Item Group", fields=["name", "parent_item_group"])}

	def category_of(group):
		seen = set()
		while group and group not in seen:
			if group in mapping:
				return mapping[group]
			seen.add(group)
			group = groups.get(group)
		return UNMAPPED

	codes = list(item_codes)
	result = {}
	for start in range(0, len(codes), 5000):
		for item in frappe.get_all(
			"Item", filters={"name": ["in", codes[start : start + 5000]]}, fields=["name", "item_group"]
		):
			result[item.name] = category_of(item.item_group)
	return result


def empty_totals():
	return frappe._dict(dict.fromkeys(VALUE_FIELDS, 0.0))


def add_movement(target, category, kind, qty, value):
	"""Add one period movement to a totals dict, in the columns this category uses."""
	in_kinds, out_kinds = BUCKETS[category][:2]
	if kind in in_kinds:
		target.in_qty += qty
		target.in_val += value
	elif kind in out_kinds:
		target.out_qty -= qty
		target.out_val -= value
	else:
		target.other_qty += qty
		target.other_val += value
	target.closing_qty += qty
	target.closing_val += value


def add_opening(target, qty, value):
	for prefix in ("opening", "closing"):
		target[f"{prefix}_qty"] += qty
		target[f"{prefix}_val"] += value


def calculate(filters):
	movements = fetch_movements(filters)
	info = get_voucher_info(movements, filters.company)
	categories = get_item_categories({m.item_code for m in movements})

	items = {}  # (category, item_code) -> totals without returns
	returns = {}  # (category, item_code, kind) -> totals of returns only
	summary = {c: empty_totals() for c in (*CATEGORIES, UNMAPPED)}
	balances = {}  # (item_code, warehouse) -> movement totals and the ledger's own running balance

	for m in movements:
		category = categories.get(m.item_code, UNMAPPED)
		key = (category, m.item_code)
		item = items.setdefault(key, empty_totals())

		balance = balances.setdefault(
			(m.item_code, m.warehouse), frappe._dict(qty=0.0, value=0.0, ledger_qty=None, ledger_val=None)
		)
		balance.qty += flt(m.qty)
		balance.value += flt(m.value)
		if m.ledger_qty is not None:
			balance.ledger_qty, balance.ledger_val = flt(m.ledger_qty), flt(m.ledger_val)

		voucher = info.get((m.vtype, m.vno))
		if not m.vno or is_opening_voucher(m.vtype, voucher):
			add_opening(item, flt(m.qty), flt(m.value))
			add_opening(summary[category], flt(m.qty), flt(m.value))
			continue

		for kind, qty, value in split_movement(m, voucher):
			add_movement(summary[category], category, kind, qty, value)
			if kind in RETURN_LABELS and kind in (*BUCKETS[category][0], *BUCKETS[category][1]):
				row = returns.setdefault((*key, kind), empty_totals())
			else:
				row = item
			add_movement(row, category, kind, qty, value)

	breakup = {}
	for category in (*CATEGORIES, UNMAPPED):
		rows = []
		for (cat, item_code), totals in sorted(items.items()):
			if cat != category:
				continue
			if has_amounts(totals):
				rows.append(frappe._dict(totals, item_code=item_code, kind=None))
			for kind in RETURN_LABELS:
				returned = returns.get((cat, item_code, kind))
				if returned and has_amounts(returned):
					rows.append(frappe._dict(returned, item_code=item_code, kind=kind))
		total = empty_totals()
		for row in rows:
			for f in VALUE_FIELDS:
				total[f] += row[f]
		breakup[category] = frappe._dict(rows=rows, total=total)

	categories_shown = list(CATEGORIES)
	if breakup[UNMAPPED].rows:
		categories_shown.append(UNMAPPED)

	grand = empty_totals()
	for category in categories_shown:
		for f in VALUE_FIELDS:
			grand[f] += summary[category][f]

	return frappe._dict(
		categories=categories_shown,
		summary=summary,
		grand=grand,
		breakup=breakup,
		differences=get_differences(categories_shown, summary, breakup),
		ledger_mismatches=get_ledger_mismatches(balances, categories),
		unmapped_items=sorted({r.item_code for r in breakup[UNMAPPED].rows}),
		show_other=any(is_significant(summary[c], "other") for c in categories_shown)
		or any(is_significant(r, "other") for c in categories_shown for r in breakup[c].rows),
		currency=frappe.get_cached_value("Company", filters.company, "default_currency"),
	)


def has_amounts(totals):
	return any(abs(totals[f]) > 1e-6 for f in VALUE_FIELDS)


def is_significant(totals, prefix):
	return abs(totals[f"{prefix}_qty"]) >= QTY_TOLERANCE or abs(totals[f"{prefix}_val"]) >= VALUE_TOLERANCE


def clean_difference(field, value):
	tolerance = QTY_TOLERANCE if field.endswith("_qty") else VALUE_TOLERANCE
	return 0.0 if abs(value) < tolerance else flt(value, 6)


def get_differences(categories, summary, breakup):
	"""Summary minus item-wise breakup, per category."""
	return {
		c: frappe._dict({f: clean_difference(f, summary[c][f] - breakup[c].total[f]) for f in VALUE_FIELDS})
		for c in categories
	}


def get_ledger_mismatches(balances, categories):
	"""Item/warehouse pairs whose movements do not add up to the ledger's stored running balance.

	That happens when a repost is pending or has failed.
	"""
	mismatches = []
	for (item_code, warehouse), b in sorted(balances.items()):
		qty = clean_difference("closing_qty", b.qty - flt(b.ledger_qty))
		value = clean_difference("closing_val", b.value - flt(b.ledger_val))
		if qty or value:
			mismatches.append(
				frappe._dict(
					item_code=item_code,
					warehouse=warehouse,
					category=categories.get(item_code, UNMAPPED),
					closing_qty=qty,
					closing_val=value,
				)
			)
	return mismatches


# --------------------------------------------------------------------------- presentation


def get_columns(show_other):
	def column(label, fieldname, fieldtype, width=120):
		c = {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
		if fieldtype == "Currency":
			c["options"] = "currency"
		return c

	columns = [column("Type / Item Code", "label", "Data", 380)]
	prefixes = [("Opening", "opening"), ("Inward", "in"), ("Outward", "out")]
	if show_other:
		prefixes.append(("Other (Net)", "other"))
	prefixes.append(("Closing", "closing"))
	for label, prefix in prefixes:
		columns.append(column(f"{label} Qty", f"{prefix}_qty", "Float", 115))
		columns.append(column(f"{label} Value", f"{prefix}_val", "Currency", 135))
	columns.append(column("Remarks", "remarks", "Data", 220))
	return columns


def header_row(first, inward, outward, category=None):
	labels = {"opening": _("Opening"), "in": inward, "out": outward, "other": _("Other (Net)"), "closing": _("Closing")}
	row = {"row_type": "header", "label": first, "category": category, "remarks": _("Remarks")}
	for prefix, label in labels.items():
		row[f"{prefix}_qty"] = f"{label} {_('Qty')}"
		row[f"{prefix}_val"] = f"{label} {_('Value')}"
	return row


def value_row(row_type, label, totals, currency, **extra):
	row = {"row_type": row_type, "label": label, "currency": currency}
	row.update({f: flt(totals[f], 6) for f in VALUE_FIELDS if f in totals})
	row.update(extra)
	return row


def text_row(row_type, label="", **extra):
	return {"row_type": row_type, "label": label, **extra}


def build_rows(filters, result):
	currency = result.currency
	rows = [
		text_row("title", filters.company),
		text_row("title", _("Stock Summary Report")),
		text_row(
			"title", _("From {0} To {1}").format(formatdate(filters.from_date), formatdate(filters.to_date))
		),
		text_row("blank"),
		text_row("section", _("STOCK SUMMARY")),
		header_row(_("Type"), _("Inward"), _("Outward")),
	]
	for category in result.categories:
		rows.append(
			value_row(
				"summary",
				_(category),
				result.summary[category],
				currency,
				category=category,
				remarks=_("Item Groups not mapped") if category == UNMAPPED else None,
			)
		)
	rows.append(value_row("total", _("Total"), result.grand, currency))

	rows += [text_row("blank"), text_row("section", _("ITEMWISE DETAILED REPORT - BREAKUP OF SUMMARY"))]
	for category in result.categories:
		inward, outward = (_(label) for label in BUCKETS[category][2:])
		rows += [
			text_row("blank"),
			text_row("section", _(category).upper(), category=category),
			header_row(_("Item Code"), inward, outward, category=category),
		]
		for item in result.breakup[category].rows:
			rows.append(
				value_row(
					"return" if item.kind else "item",
					item.item_code,
					item,
					currency,
					category=category,
					item_code=item.item_code,
					kind=item.kind,
					remarks=_(RETURN_LABELS[item.kind]) if item.kind else None,
				)
			)
		rows.append(value_row("total", _("Total"), result.breakup[category].total, currency, category=category))

	rows += [
		text_row("blank"),
		text_row("section", _("DIFFERENCE - SUMMARY VS BREAKUP")),
		header_row(_("Type"), _("Inward"), _("Outward")),
	]
	overall = empty_totals()
	for category in result.categories:
		difference = result.differences[category]
		for f in VALUE_FIELDS:
			overall[f] += difference[f]
		rows.append(
			value_row(
				"difference",
				_(category),
				difference,
				currency,
				category=category,
				remarks=_("DIFFERENCE") if any(difference.values()) else _("Matched"),
			)
		)
	rows.append(
		value_row(
			"total",
			_("Total Difference"),
			overall,
			currency,
			remarks=_("DIFFERENCE") if any(overall.values()) else _("Matched"),
		)
	)

	if result.ledger_mismatches:
		rows += [text_row("blank"), text_row("section", _("MOVEMENTS NOT MATCHING LEDGER RUNNING BALANCE"))]
		for m in result.ledger_mismatches:
			rows.append(
				{
					"row_type": "mismatch",
					"label": m.item_code,
					"item_code": m.item_code,
					"warehouse": m.warehouse,
					"category": m.category,
					"currency": currency,
					"closing_qty": m.closing_qty,
					"closing_val": m.closing_val,
					"remarks": _("{0}: check Repost Item Valuation").format(m.warehouse),
				}
			)
	return rows


def get_message(result):
	messages = []
	if result.unmapped_items:
		shown = ", ".join(escape_html(i) for i in result.unmapped_items[:10])
		if len(result.unmapped_items) > 10:
			shown += " ..."
		messages.append(
			_("{0} item(s) belong to Item Groups that are not mapped to a category: {1}").format(
				len(result.unmapped_items), shown
			)
			+ f' <a href="/app/stock-category-mapping">{_("Configure mapping")}</a>'
		)
	if result.show_other:
		messages.append(
			_(
				"Other (Net) columns hold movements outside a category's own Inward and Outward types, such as stock reconciliation, material issue or receipt and warehouse transfers. Click a value to see the vouchers."
			)
		)
	if result.ledger_mismatches:
		messages.append(
			_("{0} item/warehouse balance(s) do not match the Stock Ledger. See the end of the report.").format(
				len(result.ledger_mismatches)
			)
		)
	return "<br>".join(messages) or None


def get_report_summary(filters, result):
	reconciled = not result.ledger_mismatches and not any(
		any(d.values()) for d in result.differences.values()
	)
	return [
		{
			"label": _("Total Opening Stock"),
			"value": result.grand.opening_val,
			"datatype": "Currency",
			"currency": result.currency,
			"indicator": "Blue",
		},
		{
			"label": _("Total Closing Stock"),
			"value": result.grand.closing_val,
			"datatype": "Currency",
			"currency": result.currency,
			"indicator": "Green",
		},
		{
			"label": _("Unmapped Items"),
			"value": len(result.unmapped_items),
			"datatype": "Int",
			"indicator": "Orange" if result.unmapped_items else "Green",
		},
		{
			"label": _("Reconciliation"),
			"value": _("Matched") if reconciled else _("Check Differences"),
			"datatype": "Data",
			"indicator": "Green" if reconciled else "Red",
		},
	]


# --------------------------------------------------------------------------- drill-down


def get_transactions(filters, category=None, item_code=None, column="in", kind=None, limit=500):
	"""Ledger movements behind one figure of the report.

	``column`` is in / out / other; ``kind`` narrows to a return row, and an item row (kind None)
	leaves returns out so the list adds up to the figure that was clicked.
	"""
	filters = validate_filters(filters)
	if item_code:
		filters.item_code = item_code
	movements = fetch_movements(filters)
	info = get_voucher_info(movements, filters.company)
	categories = get_item_categories({m.item_code for m in movements})

	rows = []
	for m in movements:
		item_category = categories.get(m.item_code, UNMAPPED)
		voucher = info.get((m.vtype, m.vno))
		if not m.vno or is_opening_voucher(m.vtype, voucher) or (category and item_category != category):
			continue
		in_kinds, out_kinds = BUCKETS[item_category][:2]
		for movement_kind, qty, value in split_movement(m, voucher):
			bucket = "in" if movement_kind in in_kinds else "out" if movement_kind in out_kinds else "other"
			if bucket != column:
				continue
			if kind and movement_kind != kind:
				continue
			if item_code and not kind and movement_kind in RETURN_LABELS and bucket != "other":
				continue
			movement = movement_kind
			if movement_kind == "other":
				movement = (voucher or {}).get("purpose") or m.vtype
			rows.append(
				frappe._dict(
					posting_date=m.posting_date,
					voucher_type=m.vtype,
					voucher_no=m.vno,
					item_code=m.item_code,
					warehouse=m.warehouse,
					movement=_(movement.replace("_", " ").title() if "_" in movement or movement.islower() else movement),
					qty=flt(qty, 6),
					value=flt(value, 6),
				)
			)
	rows.sort(key=lambda r: (r.posting_date, r.voucher_no, r.item_code, r.warehouse))
	return frappe._dict(
		rows=rows[:limit],
		count=len(rows),
		qty=sum(r.qty for r in rows),
		value=sum(r.value for r in rows),
		currency=frappe.get_cached_value("Company", filters.company, "default_currency"),
	)
