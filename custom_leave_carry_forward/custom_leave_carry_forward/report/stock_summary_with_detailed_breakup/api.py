"""Whitelisted endpoints of the Category Summary view: drill-down and formatted Excel."""

from io import BytesIO

import frappe
from frappe.desk.query_report import get_report_doc
from frappe.utils import cstr

from custom_leave_carry_forward.custom_leave_carry_forward.report.stock_summary_with_detailed_breakup import (
	category_summary,
)

REPORT = "Stock Summary With Detailed Breakup"


@frappe.whitelist()
def get_transactions(filters, category=None, item_code=None, column="in", kind=None):
	get_report_doc(REPORT)  # same role and permission checks as running the report
	if column not in ("in", "out", "other"):
		frappe.throw(frappe._("Invalid column"))
	return category_summary.get_transactions(
		frappe.parse_json(filters), category=category or None, item_code=item_code or None, column=column, kind=kind or None
	)


@frappe.whitelist()
def download_excel(filters):
	get_report_doc(REPORT)
	frappe.permissions.can_export("Stock Ledger Entry", raise_exception=True)
	filters = category_summary.validate_filters(frappe.parse_json(filters))
	frappe.response["filename"] = f"stock_summary_{filters.from_date}_to_{filters.to_date}.xlsx"
	frappe.response["filecontent"] = build_workbook(filters)
	frappe.response["type"] = "binary"


def build_workbook(filters):
	"""Lay the report out like the source spreadsheet: two-level headers, bold totals."""
	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

	columns, rows = category_summary.execute(filters)[:2]
	fields = [c["fieldname"] for c in columns]
	amounts = fields[1:-1]  # between the label and the remarks

	workbook = Workbook()
	sheet = workbook.active
	sheet.title = "Stock Summary"

	thin = Side(style="thin", color="808080")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	fills = {name: PatternFill("solid", fgColor=color) for name, color in (("header", "D9E1F2"), ("total", "F2F2F2"))}
	center = Alignment(horizontal="center", vertical="center", wrap_text=True)

	def put(row, column, value, bold=False, fill=None, number_format=None, boxed=True, align=None):
		cell = sheet.cell(row=row, column=column)
		cell.value = value
		if isinstance(value, str):
			cell.data_type = "s"  # an item code starting with "=" must not become a formula
		if bold:
			cell.font = Font(bold=True)
		if fill:
			cell.fill = fills[fill]
		if number_format:
			cell.number_format = number_format
		if boxed:
			cell.border = border
		if align:
			cell.alignment = align

	line = 1
	for row in rows:
		kind = row["row_type"]
		if kind in ("title", "section"):
			put(line, 1, cstr(row["label"]), bold=True, boxed=False)
		elif kind == "header":
			put(line, 1, row["label"], bold=True, fill="header", align=center)
			put(line + 1, 1, None, fill="header")
			sheet.merge_cells(start_row=line, start_column=1, end_row=line + 1, end_column=1)
			for index in range(0, len(amounts), 2):
				column = index + 2
				group = row[amounts[index]].rsplit(" ", 1)[0]
				put(line, column, group, bold=True, fill="header", align=center)
				put(line, column + 1, None, fill="header")
				sheet.merge_cells(start_row=line, start_column=column, end_row=line, end_column=column + 1)
				put(line + 1, column, frappe._("Qty"), bold=True, fill="header", align=center)
				put(line + 1, column + 1, frappe._("Value"), bold=True, fill="header", align=center)
			last = len(fields)
			put(line, last, row["remarks"], bold=True, fill="header", align=center)
			put(line + 1, last, None, fill="header")
			sheet.merge_cells(start_row=line, start_column=last, end_row=line + 1, end_column=last)
			line += 1
		elif kind != "blank":
			total = kind == "total"
			fill = "total" if total else None
			put(line, 1, cstr(row["label"]), bold=total, fill=fill)
			for column, field in enumerate(amounts, start=2):
				number_format = "#,##0.00" if field.endswith("_val") else "#,##0.###"
				put(line, column, row.get(field), bold=total, fill=fill, number_format=number_format)
			put(line, len(fields), row.get("remarks"), bold=total, fill=fill)
		line += 1

	sheet.column_dimensions["A"].width = 34
	for index in range(2, len(fields)):
		sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = 17
	sheet.column_dimensions[sheet.cell(row=1, column=len(fields)).column_letter].width = 28
	sheet.freeze_panes = "B1"
	sheet.page_setup.orientation = "landscape"
	sheet.page_setup.fitToWidth = 1
	sheet.page_setup.fitToHeight = 0
	sheet.sheet_properties.pageSetUpPr.fitToPage = True

	output = BytesIO()
	workbook.save(output)
	return output.getvalue()
