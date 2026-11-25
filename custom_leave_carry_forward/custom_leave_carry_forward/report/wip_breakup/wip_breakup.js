// Copyright (c) 2026, Sukku and contributors
// For license information, please see license.txt

// WIP Breakup
frappe.query_reports["WIP Breakup"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "work_order",
			label: __("Work Order"),
			fieldtype: "Link",
			options: "Work Order",
			get_query: () => ({
				filters: { docstatus: 1, company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{ fieldname: "production_item", label: __("Production Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{
			fieldname: "wip_warehouse",
			label: __("WIP Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company } : {} };
			},
		},
		{
			fieldname: "status",
			label: __("Production Status"),
			fieldtype: "Select",
			options: ["", "Not Started", "In Process", "Completed", "Stopped", "Closed"],
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Work Order Summary", "Material-wise Breakup"],
			default: "Work Order Summary",
		},
	],

	after_datatable_render() {
		render_wip_charts();
	},

	formatter(value, row, column, data, default_formatter) {
		// The Total row is added by the framework (add_total_row = 1).
		// Summing a % or a per-unit rate is meaningless, so hide them there.
		if (
			data &&
			data.work_order === __("Total") &&
			["progress", "valuation_rate"].includes(column.fieldname)
		) {
			return "";
		}
		return default_formatter(value, row, column, data);
	},
};

function render_wip_charts() {
	const report = frappe.query_report;
	const extra = report.chart_options && report.chart_options.extra;
	report.page.main.find(".wip-charts").remove();
	if (!extra) return;
	report.$chart.hide();

	const $wrap = $(`
		<div class="wip-charts" style="display:grid;gap:var(--margin-md,12px);
			grid-template-columns:repeat(auto-fit,minmax(320px,1fr));padding:var(--padding-md,12px) 15px 0;">
			<div class="c-wip"></div><div class="c-pending"></div><div class="c-cons"></div>
		</div>`).insertAfter(report.$chart);

	const make = (sel, title, name, data, color) =>
		new frappe.Chart($wrap.find(sel)[0], {
			title: __(title),
			type: "bar",
			height: 240,
			colors: [color],
			axisOptions: { shortenYAxisNumbers: 1, numberFormatter: frappe.utils.format_chart_axis_number },
			data: { labels: data.labels, datasets: [{ name: __(name), values: data.values }] },
		});

	make(".c-wip", "Work Order-wise WIP Value", "WIP Value", extra.wip, "#e07b39");
	make(".c-pending", "Pending Production Quantity", "Pending Qty", extra.pending, "#4f7cff");
	make(".c-cons", "Material Consumption Value by Work Order", "Consumption Value", extra.consumption, "#2fa36b");
}