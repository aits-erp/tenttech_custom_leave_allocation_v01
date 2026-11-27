"""Stock Summary With Detailed Breakup: real stock entries, reconciled against ERPNext's own
Stock Balance report."""

import frappe
from frappe.desk.query_report import run as run_from_desk
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, flt, get_first_day, getdate, nowdate

from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.stock.report.stock_balance.stock_balance import execute as standard_stock_balance

from custom_leave_carry_forward.custom_leave_carry_forward.report.stock_summary_with_detailed_breakup import (
	stock_summary_with_detailed_breakup as report,
)
from custom_leave_carry_forward.tests import fixtures as fx

P = "MPR-SS"


def run(**filters):
	filters.setdefault("view", "Balance Listing")
	columns, data, _m, chart, summary = report.execute(filters)
	return frappe._dict(columns=columns, data=data, chart=chart, summary=summary)


def rows_of(res):
	return [r for r in res.data if not r.get("is_total_row")]


def by_key(res):
	return {(r.item_code, r.warehouse): r for r in rows_of(res)}


class TestStockSummary(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = fx.get_company()
		today = getdate(nowdate())
		cls.d1 = add_days(get_first_day(add_months(today, -1)), 4)  # last month
		cls.d2 = get_first_day(today)  # 1st of this month
		cls.d3 = today
		cls.group = fx.make_item_group(f"{P} Group")
		cls.other_group = fx.make_item_group(f"{P} Other")

		cls.parent_wh = fx.make_warehouse(cls.company, f"{P} Parent", is_group=1)
		cls.wa = fx.make_warehouse(cls.company, f"{P} A", parent=cls.parent_wh)
		cls.wb = fx.make_warehouse(cls.company, f"{P} B", parent=cls.parent_wh)
		cls.wc = fx.make_warehouse(cls.company, f"{P} C")  # outside the group

		cls.x = fx.make_item(f"{P}-X", cls.group)
		cls.y = fx.make_item(f"{P}-Y", cls.group)
		cls.z = fx.make_item(f"{P}-Z", cls.other_group)
		cls.w = fx.make_item(f"{P}-W", cls.group)  # ends at zero stock

		def se(**kw):
			return make_stock_entry(company=cls.company, set_posting_time=1, **kw)

		se(item_code=cls.x, qty=100, to_warehouse=cls.wa, rate=10, posting_date=cls.d1)
		se(item_code=cls.x, qty=50, to_warehouse=cls.wb, rate=20, posting_date=cls.d1)
		se(item_code=cls.y, qty=30, to_warehouse=cls.wa, rate=5, posting_date=cls.d1)
		se(item_code=cls.z, qty=7, to_warehouse=cls.wc, rate=3, posting_date=cls.d1)
		se(item_code=cls.w, qty=5, to_warehouse=cls.wa, rate=8, posting_date=cls.d1)
		se(item_code=cls.w, qty=5, from_warehouse=cls.wa, rate=8, posting_date=cls.d2)  # W -> 0
		# period movements
		se(item_code=cls.x, qty=20, from_warehouse=cls.wa, to_warehouse=cls.wb, posting_date=cls.d2)
		se(item_code=cls.x, qty=10, from_warehouse=cls.wa, posting_date=cls.d3)  # issue
		se(item_code=cls.x, qty=40, to_warehouse=cls.wa, rate=12, posting_date=cls.d3)
		# a receipt that gets cancelled must never show up
		bad = se(item_code=cls.x, qty=999, to_warehouse=cls.wa, rate=1, posting_date=cls.d3)
		frappe.get_doc("Stock Entry", bad.name).cancel()

	def base(self, **kw):
		f = {"company": self.company, "item_group": self.group, "to_date": self.d3}
		f.update(kw)
		return f

	# --------------------------------------------------------------- balances
	def test_current_balance(self):
		res = by_key(run(**self.base()))
		a, b = res[(self.x, self.wa)], res[(self.x, self.wb)]
		self.assertEqual((a.bal_qty, a.bal_val), (110, 1180))  # 100-20-10+40 ; 1000-200-100+480
		self.assertEqual((b.bal_qty, b.bal_val), (70, 1200))  # 50+20 ; 1000+200
		self.assertEqual((res[(self.y, self.wa)].bal_qty, res[(self.y, self.wa)].bal_val), (30, 150))
		self.assertAlmostEqual(a.val_rate, 1180 / 110)

	def test_historical_balance_ignores_later_movements(self):
		res = by_key(run(**self.base(to_date=self.d1)))
		a = res[(self.x, self.wa)]
		self.assertEqual((a.bal_qty, a.bal_val), (100, 1000))
		self.assertEqual(res[(self.x, self.wb)].bal_qty, 50)

	def test_opening_inward_outward_closing(self):
		res = by_key(run(**self.base(from_date=self.d2)))
		a, b = res[(self.x, self.wa)], res[(self.x, self.wb)]
		self.assertEqual((a.opening_qty, a.opening_val), (100, 1000))
		self.assertEqual((a.in_qty, a.in_val), (40, 480))
		self.assertEqual((a.out_qty, a.out_val), (30, 300))
		self.assertEqual((a.bal_qty, a.bal_val), (110, 1180))
		self.assertEqual(a.opening_qty + a.in_qty - a.out_qty, a.bal_qty)
		self.assertAlmostEqual(a.opening_val + a.in_val - a.out_val, a.bal_val)
		self.assertEqual((b.opening_qty, b.in_qty, b.out_qty, b.bal_qty), (50, 20, 0, 70))

	def test_columns_depend_on_from_date(self):
		with_from = [c["fieldname"] for c in run(**self.base(from_date=self.d2)).columns]
		without = [c["fieldname"] for c in run(**self.base()).columns]
		self.assertIn("opening_qty", with_from)
		self.assertNotIn("opening_qty", without)
		self.assertIn("bal_val", without)

	def test_cancelled_entry_excluded(self):
		a = by_key(run(**self.base()))[(self.x, self.wa)]
		self.assertEqual(a.bal_qty, 110)  # 999 receipt cancelled

	# ---------------------------------------------------------------- filters
	def test_item_filter(self):
		res = run(**self.base(item_code=self.y))
		self.assertEqual({r.item_code for r in rows_of(res)}, {self.y})

	def test_item_group_filter(self):
		self.assertNotIn(self.z, {r.item_code for r in rows_of(run(**self.base()))})
		res = run(**self.base(item_group=self.other_group))
		self.assertEqual({r.item_code for r in rows_of(res)}, {self.z})

	def test_warehouse_and_warehouse_group_filter(self):
		self.assertEqual({r.warehouse for r in rows_of(run(**self.base(warehouse=self.wb)))}, {self.wb})
		grp = run(**self.base(warehouse=self.parent_wh))
		self.assertEqual({r.warehouse for r in rows_of(grp)}, {self.wa, self.wb})

	def test_company_filter(self):
		other = frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name")
		if other:
			self.assertEqual(rows_of(run(**self.base(company=other))), [])
		with self.assertRaises(frappe.ValidationError):
			run(to_date=self.d3)

	def test_zero_stock_filter(self):
		self.assertNotIn(self.w, {r.item_code for r in rows_of(run(**self.base()))})
		res = by_key(run(**self.base(include_zero_stock=1)))
		self.assertEqual((res[(self.w, self.wa)].bal_qty, res[(self.w, self.wa)].bal_val), (0, 0))

	def test_stock_uom_filter(self):
		self.assertTrue(rows_of(run(**self.base(stock_uom="Nos"))))
		self.assertEqual(rows_of(run(**self.base(stock_uom="Kg"))), [])

	def test_date_validation(self):
		with self.assertRaises(frappe.ValidationError):
			run(**self.base(from_date=self.d3, to_date=self.d1))

	# --------------------------------------------------------- grouping / KPIs
	def test_group_by_views_are_consistent(self):
		base = run(**self.base(from_date=self.d2))
		total_val = sum(r.bal_val for r in rows_of(base))
		for group in ("Item", "Warehouse", "Item Group"):
			res = run(**self.base(from_date=self.d2, group_by=group))
			self.assertAlmostEqual(sum(r.bal_val for r in rows_of(res)), total_val, msg=group)
		item_view = {r.item_code: r for r in rows_of(run(**self.base(group_by="Item")))}
		self.assertEqual(item_view[self.x].bal_qty, 180)
		wh_view = {r.warehouse: r for r in rows_of(run(**self.base(group_by="Warehouse")))}
		self.assertEqual(wh_view[self.wb].bal_qty, 70)
		self.assertEqual(len(rows_of(run(**self.base(group_by="Item Group")))), 1)

	def test_kpis_and_total_row(self):
		res = run(**self.base())
		kpi = {s["label"]: s["value"] for s in res.summary}
		self.assertEqual(kpi["Total Stock Quantity"], 110 + 70 + 30)
		self.assertEqual(kpi["Total Stock Value"], 1180 + 1200 + 150)
		self.assertEqual(kpi["Total Items"], 2)
		self.assertEqual(kpi["Total Warehouses"], 2)
		# the Total row is added by Frappe when the report runs from the desk
		shown = run_from_desk(
			"Stock Summary With Detailed Breakup", filters=self.base(view="Balance Listing"), ignore_prepared_report=True
		)
		self.assertTrue(shown["add_total_row"])
		self.assertEqual(len(shown["result"]), len(rows_of(res)) + 1)
		self.assertEqual(res.chart["type"], "bar")

	# --------------------------------------------- reconcile with ERPNext's report
	def test_reconciles_with_standard_stock_balance(self):
		for from_date in (self.d1, self.d2, self.d3):
			mine = by_key(run(**self.base(from_date=from_date)))
			std = standard_stock_balance(
				frappe._dict(
					company=self.company,
					from_date=from_date,
					to_date=self.d3,
					item_group=self.group,
					include_zero_stock_items=0,
				)
			)[1]
			std = {(r["item_code"], r["warehouse"]): r for r in std}
			self.assertEqual(set(mine), set(std), from_date)
			for key, r in mine.items():
				s = std[key]
				for mine_f, std_f in (
					("opening_qty", "opening_qty"), ("opening_val", "opening_val"),
					("in_qty", "in_qty"), ("in_val", "in_val"),
					("out_qty", "out_qty"), ("out_val", "out_val"),
					("bal_qty", "bal_qty"), ("bal_val", "bal_val"),
				):
					self.assertAlmostEqual(flt(r[mine_f]), flt(s[std_f]), places=2, msg=f"{key} {mine_f} {from_date}")
