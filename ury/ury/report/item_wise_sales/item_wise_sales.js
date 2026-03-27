// Copyright (c) 2025, Tridz Technologies Pvt. Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Item Wise Sales"] = {
	"filters": [
		{
			fieldname: "start_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
		},
		{
			fieldname: "start_time",
			label: __("From Time"),
			fieldtype: "Time",
			default: "00:00:00",
			reqd: 1,
			default: "00:00:00",
		},
		{
			fieldname: "end_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "end_time",
			label: __("To Time"),
			fieldtype: "Time",
			default: "23:59:59",
			reqd: 1,
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
			reqd: 1,
		},
		{
			fieldname: "invoice_type",
			label: __("Invoice Type"),
			fieldtype: "Select",
			options: "Sales Invoice\nPOS Invoice",
			default: "Sales Invoice",
			req: 1
		}
	]
};
