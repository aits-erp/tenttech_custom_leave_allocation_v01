// Copyright (c) 2026, Sukku and contributors
// For license information, please see license.txt

// Stock Summary With Detailed Breakup
frappe.query_reports["Stock Summary With Detailed Breakup"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{
			fieldname: "warehouse",
			label: __("Warehouse / Warehouse Group"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company } : {} };
			},
		},
		{ fieldname: "stock_uom", label: __("Stock UOM"), fieldtype: "Link", options: "UOM" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Item and Warehouse", "Item", "Warehouse", "Item Group"],
			default: "Item and Warehouse",
		},
		{ fieldname: "include_zero_stock", label: __("Include Zero Stock"), fieldtype: "Check", default: 0 },
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "ledger_link") {
			// Total row (added by Frappe) has no item/warehouse -> no link
			if (!data || (!data.item_code && !data.warehouse)) return "";
			return `<a href="#" class="ssb-ledger" data-row='${encodeURIComponent(
				JSON.stringify({ i: data.item_code || "", w: data.warehouse || "" })
			)}'>${__("View Ledger")}</a>`;
		}
		return default_formatter(value, row, column, data);
	},

	onload(report) {
		// Drill down: open the standard Stock Ledger for the clicked item / warehouse
		report.page.main.on("click", "a.ssb-ledger", function (e) {
			e.preventDefault();
			const d = JSON.parse(decodeURIComponent($(this).attr("data-row")));
			const f = report.get_values();
			const to_date = f.to_date || frappe.datetime.get_today();
			const from_date =
				f.from_date || frappe.datetime.add_months(to_date, -12); // Stock Ledger needs a start date
			const route = { company: f.company, from_date, to_date };
			if (d.i) route.item_code = d.i;
			if (d.w) route.warehouse = d.w;
			frappe.set_route("query-report", "Stock Ledger", route);
		});
	},
};