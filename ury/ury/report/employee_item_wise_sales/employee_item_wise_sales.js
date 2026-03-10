// Copyright (c) 2025, Tridz Technologies Pvt. Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Item Wise Sales"] = {
  filters: [
    {
      fieldname: "start_date",
      label: __("From Date"),
      fieldtype: "Date",
      mandatory: 1,
      reqd: 1,
    },
    {
      fieldname: "end_date",
      label: __("To Date"),
      fieldtype: "Date",
      mandatory: 1,
      default: frappe.datetime.get_today(),
      reqd: 1,
    },
    {
      fieldname: "employee",
      label: __("User"),
      fieldtype: "Link",
      options: "User",
      mandatory: 1,
      reqd: 1,
    },
    {
      fieldname: "branch",
      label: __("Branch"),
      fieldtype: "Link",
      options: "Branch",
      mandatory: 1,
      reqd: 1,
    },
    {
      fieldname: "source_document",
      label: __("Source Document"),
      fieldtype: "Select",
      options: "POS Invoice\nSales Invoice",
      default: "POS Invoice",
      reqd: 1,
    },
  ],
};
