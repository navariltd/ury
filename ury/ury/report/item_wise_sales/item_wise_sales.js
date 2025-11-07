// Copyright (c) 2025, Tridz Technologies Pvt. Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Item Wise Sales"] = {
	"filters": [
		{
			fieldname: "start_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "end_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		}
	]
};
