// Copyright (c) 2026, Sukku and contributors
// For license information, please see license.txt
// Monthly Production Quantity and Value
frappe.query_reports["Monthly Production Quantity and Value"] = {
	filters: [
		{
			fieldname: "work_order",
			label: __("Work Order"),
			fieldtype: "Link",
			options: "Work Order",
			// Work Orders only make sense once submitted
			get_query: () => ({ filters: { docstatus: 1 } }),
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
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Detailed", "Monthly Summary"],
			default: "Detailed",
		},
	],

	after_datatable_render() {
		render_monthly_charts();
	},
};

function render_monthly_charts() {
	const report = frappe.query_report;
	const monthly = report.chart_options && report.chart_options.monthly;

	// Remove our previous container (re-render on every refresh)
	report.page.main.find(".mpr-charts").remove();
	if (!monthly || !monthly.labels || !monthly.labels.length) return;

	// Replace the single native chart by our three-chart grid
	report.$chart.hide();

	const $wrap = $(`
		<div class="mpr-charts" style="display:grid;gap:var(--margin-md,12px);
			grid-template-columns:repeat(auto-fit,minmax(300px,1fr));padding:var(--padding-md,12px) 15px 0;">
			<div class="mpr-chart-qty"></div>
			<div class="mpr-chart-val"></div>
			<div class="mpr-chart-trend" style="grid-column:1/-1"></div>
		</div>`).insertAfter(report.$chart);

	const common = {
		height: 240,
		axisOptions: {
			shortenYAxisNumbers: 1,
			numberFormatter: frappe.utils.format_chart_axis_number,
		},
	};
	const make = (sel, title, type, name, values, color, extra = {}) =>
		new frappe.Chart($wrap.find(sel)[0], {
			...common,
			title: __(title),
			type,
			colors: [color],
			data: { labels: monthly.labels, datasets: [{ name: __(name), values }] },
			...extra,
		});

	make(".mpr-chart-qty", "Monthly Production Quantity", "bar", "Production Quantity", monthly.qty, "#4f7cff");
	make(".mpr-chart-val", "Monthly Production Value", "bar", "Production Value", monthly.value, "#2fa36b");
	make(".mpr-chart-trend", "Production Value Trend", "line", "Production Value", monthly.value, "#e07b39", {
		lineOptions: { regionFill: 1, hideDots: 0 },
	});
}