"""Category Summary view, driven by real ERPNext documents and checked against Stock Balance.

All transactions are created inside the test transaction and rolled back.
"""

from io import BytesIO

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.stock.report.stock_balance.stock_balance import execute as standard_stock_balance
from frappe.desk.query_report import run as run_from_desk
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, flt, get_first_day, getdate, nowdate
from openpyxl import load_workbook

from custom_leave_carry_forward.custom_leave_carry_forward.report.stock_summary_with_detailed_breakup import (
	api,
	category_summary as cs,
	stock_summary_with_detailed_breakup as report,
)
from custom_leave_carry_forward.tests import fixtures as fx

P = "MPR-CS"
RM, SFG, FG, PM = cs.CATEGORIES


def make_group(name, parent="All Item Groups", is_group=0):
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent, "is_group": is_group}
		).insert()
	return name


def make_party(doctype, name):
	if not frappe.db.exists(doctype, name):
		field = "supplier_name" if doctype == "Supplier" else "customer_name"
		frappe.get_doc({"doctype": doctype, field: name}).insert()
	return name


class TestCategorySummary(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		c = cls.company = fx.get_company()
		today = getdate(nowdate())
		cls.before = add_days(get_first_day(add_months(today, -1)), 4)
		cls.start = get_first_day(today)
		cls.today = today

		cls.root = make_group(f"{P} Root", is_group=1)
		rm_parent = make_group(f"{P} RM Parent", cls.root, is_group=1)
		cls.g_rm = make_group(f"{P} RM Child", rm_parent)  # inherits the parent's mapping
		cls.g_sfg = make_group(f"{P} SFG", cls.root)
		cls.g_fg = make_group(f"{P} FG", cls.root)
		cls.g_pm = make_group(f"{P} PM", cls.root)
		cls.g_none = make_group(f"{P} Unmapped", cls.root)
		for group, category in ((rm_parent, RM), (cls.g_sfg, SFG), (cls.g_fg, FG), (cls.g_pm, PM)):
			frappe.get_doc(
				{"doctype": "Stock Category Mapping", "item_group": group, "category": category}
			).insert()

		cls.parent_wh = fx.make_warehouse(c, f"{P} Parent", is_group=1)
		cls.stores = fx.make_warehouse(c, f"{P} Stores", parent=cls.parent_wh)
		cls.wip = fx.make_warehouse(c, f"{P} WIP", parent=cls.parent_wh)
		cls.depot = fx.make_warehouse(c, f"{P} Depot")  # outside the group

		cls.rm = fx.make_item(f"{P}-RM", cls.g_rm)
		cls.rm_adj = fx.make_item(f"{P}-RM-ADJ", cls.g_rm)
		cls.sfg = fx.make_item(f"{P}-SFG", cls.g_sfg)
		cls.fg = fx.make_item(f"{P}-FG", cls.g_fg)
		cls.pm = fx.make_item(f"{P}-PM", cls.g_pm)
		cls.other = fx.make_item(f"{P}-OTHER", cls.g_none)
		cls.zero = fx.make_item(f"{P}-ZERO", cls.g_pm)
		cls.opening_item = fx.make_item(f"{P}-OPEN", cls.g_pm)

		supplier = make_party("Supplier", f"{P} Supplier")
		customer = make_party("Customer", f"{P} Customer")

		def entry(**kw):
			return make_stock_entry(company=c, set_posting_time=1, **kw)

		# ---- opening stock (last month)
		for item, qty, rate in (
			(cls.rm, 100, 10),
			(cls.rm_adj, 40, 5),
			(cls.sfg, 20, 30),
			(cls.fg, 15, 50),
			(cls.pm, 200, 2),
			(cls.zero, 5, 4),
		):
			entry(item_code=item, qty=qty, to_warehouse=cls.stores, rate=rate, posting_date=cls.before)

		def buy(item, qty, rate, time):
			doc = frappe.get_doc(
				{
					"doctype": "Purchase Receipt",
					"company": c,
					"supplier": supplier,
					"set_posting_time": 1,
					"posting_date": cls.start,
					"posting_time": time,
					"items": [{"item_code": item, "qty": qty, "rate": rate, "warehouse": cls.stores}],
				}
			).insert()
			doc.submit()
			return doc

		def send_back(doc, qty, time):
			returned = make_return_doc(doc.doctype, doc.name)
			returned.set_posting_time = 1
			returned.posting_date = cls.start
			returned.posting_time = time
			returned.items[0].qty = -qty
			if returned.items[0].meta.has_field("received_qty"):
				returned.items[0].received_qty = -qty
			returned.items[0].stock_qty = -qty
			returned.insert()
			returned.submit()
			return returned

		# ---- purchases and a purchase return
		cls.pr = buy(cls.rm, 100, 12, "01:00:00")
		buy(cls.pm, 100, 2, "01:10:00")
		send_back(cls.pr, 10, "02:00:00")

		# ---- production: RM -> SFG (through WIP), then SFG + PM -> FG
		def produce(item, components, qty, time, transfer=True):
			bom = fx.make_bom(c, item, components)
			wo = fx.make_work_order(
				c, item, bom, qty, cls.stores, cls.wip, cls.stores, skip_transfer=not transfer, multi_level=0
			)
			purposes = ["Material Transfer for Manufacture", "Manufacture"] if transfer else ["Manufacture"]
			names = []
			for index, purpose in enumerate(purposes):
				doc = frappe.get_doc(
					fx.make_wo_stock_entry(wo, purpose, qty)
				)
				if not transfer and purpose == "Manufacture":
					for row in doc.items:
						if not row.is_finished_item:
							row.s_warehouse = cls.stores
				doc.set_posting_time = 1
				doc.posting_date = cls.start
				doc.posting_time = f"{time}:{index * 10:02d}:00"
				doc.insert()
				doc.submit()
				names.append(doc.name)
			return names

		cls.sfg_entries = produce(cls.sfg, [(cls.rm, 2)], 30, "03", transfer=True)  # RM out 60
		produce(cls.fg, [(cls.sfg, 1), (cls.pm, 3)], 25, "04", transfer=False)  # SFG out 25, PM out 75

		# ---- sales, sales return, invoice that updates stock
		dn = frappe.get_doc(
			{
				"doctype": "Delivery Note",
				"company": c,
				"customer": customer,
				"set_posting_time": 1,
				"posting_date": cls.start,
				"posting_time": "05:00:00",
				"items": [{"item_code": cls.fg, "qty": 12, "rate": 90, "warehouse": cls.stores}],
			}
		).insert()
		dn.submit()
		send_back(dn, 2, "06:00:00")
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": c,
				"customer": customer,
				"update_stock": 1,
				"set_posting_time": 1,
				"posting_date": cls.start,
				"posting_time": "07:00:00",
				"due_date": add_days(cls.start, 30),
				"items": [{"item_code": cls.fg, "qty": 3, "rate": 90, "warehouse": cls.stores}],
			}
		).insert()
		si.submit()

		# ---- reconciliation, adjustment, internal transfer
		def reconcile(item, qty, rate, time, purpose="Stock Reconciliation", **extra):
			doc = frappe.get_doc(
				{
					"doctype": "Stock Reconciliation",
					"company": c,
					"purpose": purpose,
					"set_posting_time": 1,
					"posting_date": cls.start,
					"posting_time": time,
					"items": [{"item_code": item, "warehouse": cls.stores, "qty": qty, "valuation_rate": rate}],
					**extra,
				}
			).insert()
			doc.submit()
			return doc

		cls.reco = reconcile(cls.rm_adj, 33, 6, "08:00:00")  # 40 @5 -> 33 @6
		temporary = frappe.db.get_value("Account", {"company": c, "account_type": "Temporary", "is_group": 0})
		reconcile(cls.opening_item, 50, 3, "08:30:00", purpose="Opening Stock", expense_account=temporary)

		entry(item_code=cls.pm, qty=5, from_warehouse=cls.stores, posting_date=cls.start, posting_time="09:00:00")
		entry(
			item_code=cls.rm, qty=20, from_warehouse=cls.stores, to_warehouse=cls.depot,
			posting_date=cls.start, posting_time="10:00:00",
		)  # fmt: skip
		entry(item_code=cls.other, qty=9, to_warehouse=cls.stores, rate=7, posting_date=cls.today)
		entry(item_code=cls.zero, qty=5, from_warehouse=cls.stores, posting_date=cls.start)
		cancelled = entry(item_code=cls.rm, qty=999, to_warehouse=cls.stores, rate=1, posting_date=cls.today)
		frappe.get_doc("Stock Entry", cancelled.name).cancel()

	# ------------------------------------------------------------------ helpers
	def filters(self, **kw):
		f = {"company": self.company, "item_group": self.root, "from_date": self.start, "to_date": self.today}
		f.update(kw)
		return frappe._dict(f)

	def calc(self, **kw):
		return cs.calculate(cs.validate_filters(self.filters(**kw)))

	def row(self, result, category, item, kind=None):
		found = [r for r in result.breakup[category].rows if r.item_code == item and r.kind == kind]
		self.assertEqual(len(found), 1, f"{category} {item} {kind}")
		return found[0]

	def assert_qty(self, row, opening=0, in_=0, out=0, other=0, closing=0):
		got = (row.opening_qty, row.in_qty, row.out_qty, row.other_qty, row.closing_qty)
		self.assertEqual(tuple(flt(v, 3) for v in got), (opening, in_, out, other, closing))

	def assert_foots(self, row):
		self.assertAlmostEqual(row.opening_qty + row.in_qty - row.out_qty + row.other_qty, row.closing_qty, 4)
		self.assertAlmostEqual(row.opening_val + row.in_val - row.out_val + row.other_val, row.closing_val, 4)

	# ---------------------------------------------------------------- movements
	def test_raw_material_purchase_return_consumption_transfer(self):
		res = self.calc()
		main = self.row(res, RM, self.rm)
		returned = self.row(res, RM, self.rm, "purchase_return")
		# WIP and Depot transfers net to zero for the company; 60 consumed by Manufacture
		self.assert_qty(main, opening=100, in_=100, out=60, closing=140)
		self.assert_qty(returned, in_=-10, closing=-10)
		self.assertAlmostEqual(main.in_val, 1200)
		self.assertLess(returned.in_val, 0)
		self.assertAlmostEqual(main.closing_qty + returned.closing_qty, 130)

	def test_semi_finished_production_and_consumption(self):
		self.assert_qty(self.row(self.calc(), SFG, self.sfg), opening=20, in_=30, out=25, closing=25)

	def test_finished_goods_production_sales_and_return(self):
		res = self.calc()
		main = self.row(res, FG, self.fg)
		returned = self.row(res, FG, self.fg, "sales_return")
		self.assert_qty(main, opening=15, in_=25, out=15, closing=25)  # DN 12 + invoice 3
		self.assert_qty(returned, out=-2, closing=2)  # a sales return adds stock back
		self.assertLess(returned.out_val, 0)
		self.assertEqual(res.summary[FG].out_qty, 13)

	def test_packing_material_and_stock_adjustment(self):
		self.assert_qty(
			self.row(self.calc(), PM, self.pm), opening=200, in_=100, out=75, other=-5, closing=220
		)

	def test_stock_reconciliation_uses_balance_difference(self):
		row = self.row(self.calc(), RM, self.rm_adj)
		self.assert_qty(row, opening=40, other=-7, closing=33)
		self.assertAlmostEqual(row.closing_val, 198)

	def test_listing_view_also_handles_reconciliation(self):
		data = report.execute(dict(self.filters(item_code=self.rm_adj), view="Balance Listing"))[1]
		self.assertEqual((data[0].bal_qty, data[0].out_qty), (33, 7))

	def test_opening_stock_voucher_in_period_counts_as_opening(self):
		self.assert_qty(self.row(self.calc(), PM, self.opening_item), opening=50, closing=50)

	def test_zero_closing_and_cancelled_entries(self):
		res = self.calc()
		self.assert_qty(self.row(res, PM, self.zero), opening=5, other=-5, closing=0)
		self.assertAlmostEqual(self.row(res, RM, self.rm).in_val, 1200)  # cancelled receipt absent
		later = self.calc(from_date=add_days(self.today, 1), to_date=add_days(self.today, 1))
		self.assertNotIn(self.zero, [r.item_code for r in later.breakup[PM].rows])

	# ------------------------------------------------------------- categories
	def test_mapping_inheritance_override_and_unmapped(self):
		res = self.calc()
		self.assertEqual(res.categories, [*cs.CATEGORIES, cs.UNMAPPED])
		self.assertEqual(res.unmapped_items, [self.other])
		self.assert_qty(self.row(res, cs.UNMAPPED, self.other), other=9, closing=9)
		self.assertIn(self.rm, [r.item_code for r in res.breakup[RM].rows])

		frappe.get_doc({"doctype": "Stock Category Mapping", "item_group": self.g_rm, "category": PM}).insert()
		try:
			self.assertEqual(cs.get_item_categories({self.rm})[self.rm], PM)  # nearest mapping wins
		finally:
			frappe.delete_doc("Stock Category Mapping", self.g_rm)

	def test_one_mapping_per_item_group(self):
		with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
			frappe.get_doc(
				{"doctype": "Stock Category Mapping", "item_group": self.g_pm, "category": RM}
			).insert()

	# ----------------------------------------------------------------- filters
	def test_item_item_group_and_company_filters(self):
		res = self.calc(item_code=self.pm)
		self.assertEqual({r.item_code for c in res.categories for r in res.breakup[c].rows}, {self.pm})
		res = self.calc(item_group=self.g_fg)
		self.assertEqual({r.item_code for c in res.categories for r in res.breakup[c].rows}, {self.fg})
		other = frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name")
		if other:
			self.assertEqual(self.calc(company=other).grand.closing_qty, 0)
		with self.assertRaises(frappe.ValidationError):
			cs.execute({"to_date": self.today})
		with self.assertRaises(frappe.ValidationError):
			self.calc(from_date=self.today, to_date=self.before)

	def test_warehouse_filter_shows_transfers_as_other(self):
		depot = self.row(self.calc(warehouse=self.depot), RM, self.rm)
		self.assert_qty(depot, other=20, closing=20)
		stores = self.row(self.calc(warehouse=self.stores), RM, self.rm)
		# 60 to WIP and 20 to the depot; the 10 returned are on the Purchase Return row
		self.assert_qty(stores, opening=100, in_=100, other=-80, closing=120)
		group = self.row(self.calc(warehouse=self.parent_wh), RM, self.rm)  # Stores + WIP
		self.assert_qty(group, opening=100, in_=100, out=60, other=-20, closing=120)

	def test_historical_date_ignores_later_movements(self):
		res = self.calc(from_date=get_first_day(self.before), to_date=self.before)
		self.assert_qty(self.row(res, RM, self.rm), other=100, closing=100)
		self.assertEqual(res.summary[SFG].closing_qty, 20)

	def test_default_from_date_is_month_start(self):
		f = cs.validate_filters({"company": self.company, "to_date": self.today})
		self.assertEqual(f.from_date, self.start)

	# ---------------------------------------------------------- reconciliation
	def test_summary_totals_and_differences(self):
		res = self.calc()
		for category in res.categories:
			total = res.breakup[category].total
			self.assert_foots(res.summary[category])
			for row in res.breakup[category].rows:
				self.assert_foots(row)
			for field in cs.VALUE_FIELDS:
				self.assertAlmostEqual(res.summary[category][field], total[field], 4, f"{category} {field}")
				self.assertEqual(res.differences[category][field], 0)
		for field in cs.VALUE_FIELDS:
			self.assertAlmostEqual(res.grand[field], sum(res.summary[c][field] for c in res.categories), 4)
		self.assertEqual(res.ledger_mismatches, [])

	def test_difference_and_ledger_mismatch_are_reported(self):
		summary = {c: cs.empty_totals() for c in cs.CATEGORIES}
		breakup = {c: frappe._dict(total=cs.empty_totals()) for c in cs.CATEGORIES}
		breakup[RM].total.closing_val = 5
		self.assertEqual(cs.get_differences(cs.CATEGORIES, summary, breakup)[RM].closing_val, -5)

		name = frappe.get_all(
			"Stock Ledger Entry",
			filters={"item_code": self.sfg, "is_cancelled": 0},
			order_by="posting_datetime desc, creation desc",
			limit=1,
		)[0].name
		old = frappe.db.get_value("Stock Ledger Entry", name, "stock_value")
		frappe.db.set_value("Stock Ledger Entry", name, "stock_value", old + 100, update_modified=False)
		try:
			res = self.calc()
			self.assertEqual([(m.item_code, m.closing_val) for m in res.ledger_mismatches], [(self.sfg, -100)])
			data = cs.execute(self.filters())[1]
			self.assertIn("mismatch", [r["row_type"] for r in data])
		finally:
			frappe.db.set_value("Stock Ledger Entry", name, "stock_value", old, update_modified=False)

	def test_matches_standard_stock_balance(self):
		for filters in ({}, {"warehouse": self.stores}, {"from_date": get_first_day(self.before)}):
			mine = {}
			res = self.calc(**filters)
			for category in res.categories:
				for r in res.breakup[category].rows:
					t = mine.setdefault(r.item_code, [0, 0, 0, 0])
					for i, field in enumerate(("opening_qty", "opening_val", "closing_qty", "closing_val")):
						t[i] += r[field]
			f = self.filters(**filters, include_zero_stock_items=1)
			if f.get("warehouse"):
				f.warehouse = [f.warehouse]
			theirs = {}
			for r in standard_stock_balance(f)[1]:
				t = theirs.setdefault(r["item_code"], [0, 0, 0, 0])
				for i, field in enumerate(("opening_qty", "opening_val", "bal_qty", "bal_val")):
					t[i] += flt(r[field])
			theirs = {k: v for k, v in theirs.items() if any(abs(x) > 0.001 for x in v)}
			mine = {k: v for k, v in mine.items() if any(abs(x) > 0.001 for x in v)}
			self.assertEqual(set(mine), set(theirs), filters)
			for item, values in mine.items():
				for got, expected in zip(values, theirs[item], strict=True):
					self.assertAlmostEqual(got, expected, 2, f"{item} {filters}")

	# ------------------------------------------------- layout, drill-down, Excel
	def test_report_layout(self):
		columns, data, message, _chart, summary, skip_total = report.execute(self.filters())
		sections = [r["label"] for r in data if r["row_type"] == "section"]
		self.assertEqual(
			sections,
			[
				"STOCK SUMMARY",
				"ITEMWISE DETAILED REPORT - BREAKUP OF SUMMARY",
				"RAW MATERIAL",
				"SEMI FINISHED GOODS",
				"FINISHED GOODS",
				"PACKING MATERIAL",
				"UNMAPPED",
				"DIFFERENCE - SUMMARY VS BREAKUP",
			],
		)
		headers = [r for r in data if r["row_type"] == "header"]
		self.assertEqual((headers[1]["in_qty"], headers[1]["out_qty"]), ("Purchase Qty", "Consumption Qty"))
		self.assertEqual((headers[3]["in_qty"], headers[3]["out_qty"]), ("Production Qty", "Sales Qty"))
		self.assertEqual(data[0]["label"], self.company)
		self.assertIn("not mapped", message)
		self.assertTrue(skip_total)
		self.assertEqual({s["label"] for s in summary} & {"Total Opening Stock", "Total Closing Stock"},
			{"Total Opening Stock", "Total Closing Stock"})  # fmt: skip

	def test_no_automatic_total_row_in_category_view(self):
		shown = run_from_desk(
			"Stock Summary With Detailed Breakup", filters=self.filters(), ignore_prepared_report=True
		)
		self.assertFalse(shown["add_total_row"])
		self.assertEqual(len(shown["result"]), len(cs.execute(self.filters())[1]))

	def test_other_columns_only_when_needed(self):
		fields = [c["fieldname"] for c in cs.execute(self.filters(item_code=self.sfg))[0]]
		self.assertNotIn("other_qty", fields)
		self.assertIn("other_qty", [c["fieldname"] for c in cs.execute(self.filters())[0]])

	def test_drill_down_adds_up_to_the_figure(self):
		res = self.calc()
		cases = (
			(RM, self.rm, "in", None, self.row(res, RM, self.rm).in_qty),
			(RM, self.rm, "in", "purchase_return", -10),
			(RM, self.rm, "out", None, -60),
			(FG, self.fg, "out", None, -15),
			(FG, self.fg, "out", "sales_return", 2),
			(PM, self.pm, "other", None, -5),
			(FG, None, "out", None, -13),
		)
		for category, item, column, kind, qty in cases:
			out = cs.get_transactions(self.filters(), category=category, item_code=item, column=column, kind=kind)
			self.assertAlmostEqual(out.qty, qty, 4, f"{category} {item} {column} {kind}")
		movements = cs.get_transactions(self.filters(), category=RM, item_code=self.rm_adj, column="other")
		self.assertEqual([m.voucher_no for m in movements.rows], [self.reco.name])

	def test_formatted_excel(self):
		content = api.build_workbook(cs.validate_filters(self.filters()))
		sheet = load_workbook(BytesIO(content)).active
		self.assertEqual(sheet["A1"].value, self.company)
		texts = [cell.value for cell in sheet["A"] if cell.value]
		for label in ("STOCK SUMMARY", "RAW MATERIAL", "DIFFERENCE - SUMMARY VS BREAKUP", self.rm):
			self.assertIn(label, texts)
		self.assertTrue(sheet.merged_cells.ranges)

	# ------------------------------------------------------------- permissions
	def test_user_permissions_and_roles(self):
		user = f"{P.lower()}@example.com"
		if not frappe.db.exists("User", user):
			doc = frappe.get_doc({"doctype": "User", "email": user, "first_name": P, "send_welcome_email": 0})
			doc.append("roles", {"role": "Stock User"})
			doc.insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Warehouse", "for_value": self.depot}
		).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			self.assertEqual(self.calc().grand.closing_qty, 20)  # only the depot transfer is visible
			listing = report.execute(dict(self.filters(), view="Balance Listing"))[1]
			self.assertEqual(listing[-1]["bal_qty"], 20)
		finally:
			frappe.set_user("Administrator")

		outsider = f"{P.lower()}-none@example.com"
		if not frappe.db.exists("User", outsider):
			frappe.get_doc(
				{"doctype": "User", "email": outsider, "first_name": P, "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(outsider)
		try:
			with self.assertRaises(frappe.PermissionError):
				api.get_transactions(frappe.as_json(self.filters()))
			with self.assertRaises(frappe.PermissionError):
				api.download_excel(frappe.as_json(self.filters()))
		finally:
			frappe.set_user("Administrator")
