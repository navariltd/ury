# Copyright (c) 2025, Tridz Technologies Pvt. Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint


def execute(filters=None):
    # normalize and validate filters
    filters = apply_filters(filters)
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    """
    Return report column definitions.
    """
    return [
        {
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 350,
        },
        {"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
        {
            "label": _("Amount"),
            "fieldname": "amount",
            "fieldtype": "Currency",
            "width": 120,
        },
    ]


def apply_filters(filters):
    """
    Validate and prepare filters for SQL.
    Required: start_date, end_date, branch
    """
    if filters is None:
        filters = {}

    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    branch = filters.get("branch")

    if not start_date:
        frappe.throw(_("Please select From Date"), exc=frappe.ValidationError)
    if not end_date:
        frappe.throw(_("Please select To Date"), exc=frappe.ValidationError)
    if not branch:
        frappe.throw(_("Please select Branch"), exc=frappe.ValidationError)


    # return a clean dict used for SQL params
    return {"start_date": start_date, "end_date": end_date, "branch": branch}


def get_data(filters):
    """
    Execute the SQL (adapted from the original query) and return list of dicts.
    """
    sql = """
	SELECT 
		c.`item_group` AS item_group,
		c.`item_name` AS item_name,
		SUM(b.`qty`) AS qty,
		SUM(b.`amount`) AS amount
	FROM 
		(
			SELECT %(start_date)s AS `date`
			UNION
			SELECT DATE_ADD(%(start_date)s, INTERVAL n DAY) AS `date`
			FROM (
				SELECT a.N + b.N * 10 + c.N * 100 + 1 AS n
				FROM (
					SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9
				) AS a
				CROSS JOIN (
					SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9
				) AS b
				CROSS JOIN (
					SELECT 0 AS N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9
				) AS c
				ORDER BY n
			) AS nums
			WHERE DATE_ADD(%(start_date)s, INTERVAL n DAY) < %(end_date)s
			UNION
			SELECT %(end_date)s AS `date`
		) AS date_list
	LEFT JOIN `tabPOS Invoice` a ON (
		a.`branch` = %(branch)s
		AND a.`status` IN ("Consolidated","Paid") 
		AND a.`docstatus` = 1 
	)
	INNER JOIN `tabPOS Invoice Item` b ON a.`name`=b.`parent`
	LEFT JOIN `tabItem` c ON c.`item_code` = b.`item_code`
	LEFT JOIN `tabURY Report Settings` rs ON (
		rs.`branch` = %(branch)s
	)
	WHERE
	(
		((rs.`hours` IS NULL OR rs.`hours` = 0) AND a.`posting_date` = date_list.`date`)
		OR (rs.`hours` > 0 AND TIMESTAMP(a.`posting_date`, a.`posting_time`) <= TIMESTAMP(DATE_ADD(date_list.`date`, INTERVAL 1 DAY), CONCAT(LPAD(rs.`hours`, 2, '0'), ':00:00')) AND TIMESTAMP(a.`posting_date`, a.`posting_time`) >= TIMESTAMP(date_list.`date`, CONCAT(LPAD(rs.`hours`, 2, '0'), ':00:00')))
		OR (rs.`branch` IS NULL AND a.`posting_date` = date_list.`date`)
	)
	GROUP BY 
		c.`item_name`
	ORDER BY 
		c.`item_group` ASC, b.`item_name` ASC
	"""
    # execute query with named params and return as dicts
    results = frappe.db.sql(sql, filters, as_dict=True)

    # normalize any NULLs if desired (optional)
    for r in results:
        if r.get("item_group") is None:
            r["item_group"] = ""
        if r.get("item_name") is None:
            r["item_name"] = ""
        # qty/amount may be None when no rows; coerce to 0
        r["qty"] = r.get("qty") or 0
        r["amount"] = r.get("amount") or 0.0

    return results
