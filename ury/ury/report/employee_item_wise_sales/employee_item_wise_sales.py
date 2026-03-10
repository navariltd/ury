# Copyright (c) 2025, Tridz Technologies Pvt. Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = apply_filters(filters)
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
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
	if filters is None:
		filters = {}

	start_date = filters.get("start_date")
	end_date = filters.get("end_date")
	branch = filters.get("branch")
	employee = filters.get("employee")

	if not start_date:
		frappe.throw(_("Please select From Date"), exc=frappe.ValidationError)
	if not end_date:
		frappe.throw(_("Please select To Date"), exc=frappe.ValidationError)
	if not branch:
		frappe.throw(_("Please select Branch"), exc=frappe.ValidationError)
	if not employee:
		frappe.throw(_("Please select User"), exc=frappe.ValidationError)

	return {
		"start_date": start_date,
		"end_date": end_date,
		"branch": branch,
		"employee": employee,
	}


def get_data(filters):
	sql = """
    SELECT
        i.`item_group` AS item_group,
        b.`item_name` AS item_name,
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
    LEFT JOIN `tabURY Report Settings` rs ON (
        rs.`branch` = %(branch)s
    )
    INNER JOIN `tabPOS Invoice Item` b ON (
        a.name = b.parent
    )
    INNER JOIN `tabUser` e ON (
        e.`name` = %(employee)s
        AND e.`name` = a.`waiter`
    )
    INNER JOIN `tabItem` i ON (
        b.`item_code` = i.`item_code`
    )
    WHERE
    (
        ((rs.`hours` IS NULL OR rs.`hours` = 0) AND a.`posting_date` = date_list.`date`)
        OR (rs.`hours` > 0 AND TIMESTAMP(a.`posting_date`, a.`posting_time`) <= TIMESTAMP(DATE_ADD(date_list.`date`, INTERVAL 1 DAY), CONCAT(LPAD(rs.`hours`, 2, '0'), ':00:00')) AND TIMESTAMP(a.`posting_date`, a.`posting_time`) >= TIMESTAMP(date_list.`date`, CONCAT(LPAD(rs.`hours`, 2, '0'), ':00:00')))
        OR (rs.`branch` IS NULL AND a.`posting_date` = date_list.`date`)
    )
    GROUP BY
        b.`item_name`, i.`item_group`
    ORDER BY
        i.`item_group` ASC, b.`item_name` ASC
    """
	results = frappe.db.sql(sql, filters, as_dict=True)

	for r in results:
		if r.get("item_group") is None:
			r["item_group"] = ""
		if r.get("item_name") is None:
			r["item_name"] = ""
		r["qty"] = r.get("qty") or 0
		r["amount"] = r.get("amount") or 0.0

	return results
