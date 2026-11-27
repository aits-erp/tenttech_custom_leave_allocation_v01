// Copyright (c) 2026, Sukku and contributors
// For license information, please see license.txt

// Stock Summary With Detailed Breakup
(() => {
	const REPORT = "Stock Summary With Detailed Breakup";
	const API =
		"custom_leave_carry_forward.custom_leave_carry_forward.report.stock_summary_with_detailed_breakup.api";
	const LISTING_ONLY = "eval:doc.view == 'Balance Listing'";

	const is_category_view = () => frappe.query_report.get_filter_value("view") !== "Balance Listing";
	const escape = (value) => frappe.utils.escape_html(cstr(value));

	function show_transactions(data, column) {
		const filters = frappe.query_report.get_filter_values();
		frappe.call({
			method: `${API}.get_transactions`,
			args: {
				filters,
				category: data.category,
				item_code: data.item_code,
				column,
				kind: data.kind,
			},
			freeze: true,
			callback: ({ message }) => {
				const money = (v) => format_currency(v, message.currency);
				const body = message.rows
					.map(
						(r) => `<tr>
							<td>${frappe.datetime.str_to_user(r.posting_date)}</td>
							<td><a href="${frappe.utils.get_form_link(r.voucher_type, r.voucher_no)}" target="_blank">${escape(r.voucher_no)}</a><br>
								<small class="text-muted">${escape(__(r.voucher_type))}</small></td>
							<td>${escape(r.movement)}</td>
							<td>${escape(r.item_code)}</td>
							<td>${escape(r.warehouse)}</td>
							<td class="text-right">${format_number(r.qty)}</td>
							<td class="text-right">${money(r.value)}</td>
						</tr>`
					)
					.join("");
				const more =
					message.count > message.rows.length
						? `<p class="text-muted">${__("Showing {0} of {1} movements. Totals cover all of them.", [message.rows.length, message.count])}</p>`
						: "";
				const dialog = new frappe.ui.Dialog({
					title: [data.item_code || __(data.category || "All Categories"), __("Transactions")].join(" - "),
					size: "extra-large",
				});
				dialog.$body.html(
					`${more}<div style="overflow:auto"><table class="table table-bordered table-sm">
						<thead><tr><th>${__("Date")}</th><th>${__("Voucher")}</th><th>${__("Movement")}</th>
						<th>${__("Item")}</th><th>${__("Warehouse")}</th><th class="text-right">${__("Qty (+ in / - out)")}</th>
						<th class="text-right">${__("Value")}</th></tr></thead>
						<tbody>${body || `<tr><td colspan="7" class="text-muted">${__("No movements")}</td></tr>`}</tbody>
						<tfoot><tr><th colspan="5">${__("Total")}</th><th class="text-right">${format_number(message.qty)}</th>
						<th class="text-right">${money(message.value)}</th></tr></tfoot>
					</table></div>`
				);
				dialog.show();
			},
		});
	}

	function stock_ledger_link(data) {
		return `<a href="#" class="ssb-ledger" data-row='${encodeURIComponent(
			JSON.stringify({ i: data.item_code || "", w: data.warehouse || "" })
		)}'>${escape(data.label || __("View Ledger"))}</a>`;
	}

	function format_category_cell(value, row, column, data, default_formatter) {
		const field = column.fieldname;
		const type = data.row_type;

		if (type === "header") {
			return `<strong>${escape(data[field] || "")}</strong>`;
		}
		if (field === "label") {
			if (["item", "return", "mismatch"].includes(type)) return stock_ledger_link(data);
			return ["title", "section", "total"].includes(type)
				? `<strong>${escape(data.label || "")}</strong>`
				: escape(data.label || "");
		}
		if (field === "remarks") {
			const text = escape(data.remarks || "");
			return data.remarks === __("DIFFERENCE") ? `<span class="text-danger"><strong>${text}</strong></span>` : text;
		}
		if (data[field] === undefined || data[field] === null) return "";

		let html = default_formatter(value, row, column, data);
		const bucket = field.replace(/_(qty|val)$/, "");
		if (["summary", "item", "return"].includes(type) && ["in", "out", "other"].includes(bucket) && data[field]) {
			html = `<a href="#" class="ssb-drill" data-column="${bucket}" data-row='${encodeURIComponent(
				JSON.stringify({ category: data.category, item_code: data.item_code || "", kind: data.kind || "" })
			)}'>${$(`<div>${html}</div>`).text()}</a>`;
			html = `<div style="text-align:right">${html}</div>`;
		}
		if (type === "difference" && data[field]) html = `<span class="text-danger">${html}</span>`;
		if (type === "total") html = `<strong>${html}</strong>`;
		return html;
	}

	frappe.query_reports[REPORT] = {
		filters: [
			{
				fieldname: "view",
				label: __("View"),
				fieldtype: "Select",
				options: ["Category Summary", "Balance Listing"],
				default: "Category Summary",
			},
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				default: frappe.defaults.get_user_default("Company"),
				reqd: 1,
			},
			{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
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
			{ fieldname: "stock_uom", label: __("Stock UOM"), fieldtype: "Link", options: "UOM", depends_on: LISTING_ONLY },
			{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", depends_on: LISTING_ONLY },
			{
				fieldname: "group_by",
				label: __("Group By"),
				fieldtype: "Select",
				options: ["Item and Warehouse", "Item", "Warehouse", "Item Group"],
				default: "Item and Warehouse",
				depends_on: LISTING_ONLY,
			},
			{
				fieldname: "include_zero_stock",
				label: __("Include Zero Stock"),
				fieldtype: "Check",
				default: 0,
				depends_on: LISTING_ONLY,
			},
		],

		formatter(value, row, column, data, default_formatter) {
			if (data && data.row_type) {
				return format_category_cell(value, row, column, data, default_formatter);
			}
			if (column.fieldname === "ledger_link") {
				if (!data || (!data.item_code && !data.warehouse)) return ""; // total row
				return stock_ledger_link({ item_code: data.item_code, warehouse: data.warehouse });
			}
			return default_formatter(value, row, column, data);
		},

		get_datatable_options(options) {
			// sorting would scramble the sections of the category view
			if (is_category_view()) {
				options.columns.forEach((column) => (column.sortable = false));
			}
			return options;
		},

		onload(report) {
			// Drill down: open the standard Stock Ledger for the clicked item / warehouse
			report.page.main.on("click", "a.ssb-ledger", function (e) {
				e.preventDefault();
				const d = JSON.parse(decodeURIComponent($(this).attr("data-row")));
				const f = report.get_filter_values();
				const to_date = f.to_date || frappe.datetime.get_today();
				const from_date = f.from_date || frappe.datetime.add_months(to_date, -12); // Stock Ledger needs a start date
				const route = { company: f.company, from_date, to_date };
				if (d.i) route.item_code = d.i;
				if (d.w || f.warehouse) route.warehouse = d.w || f.warehouse;
				frappe.set_route("query-report", "Stock Ledger", route);
			});

			report.page.main.on("click", "a.ssb-drill", function (e) {
				e.preventDefault();
				show_transactions(
					JSON.parse(decodeURIComponent($(this).attr("data-row"))),
					$(this).attr("data-column")
				);
			});

			report.page.add_inner_button(__("Download Excel (Report Format)"), () => {
				if (!is_category_view()) {
					frappe.msgprint(__("The formatted Excel is available in the Category Summary view."));
					return;
				}
				const filters = JSON.stringify(report.get_filter_values(true));
				window.open(`/api/method/${API}.download_excel?filters=${encodeURIComponent(filters)}`);
			});
			report.page.add_inner_button(__("Category Mapping"), () =>
				frappe.set_route("List", "Stock Category Mapping")
			);
		},
	};
})();
