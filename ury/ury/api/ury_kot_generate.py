import json

import frappe
from frappe import _
from frappe.utils import flt

from ury.ury.production_routing import get_item_production_map, get_production_units


def load_json(data):
	return json.loads(data) if isinstance(data, str) else data


def create_order_items(items):
	order_items = []
	for index, item in enumerate(items or []):
		item_code = item.get("item", item.get("item_code"))
		order_items.append({
			"item_code": item_code,
			"qty": flt(item.get("qty")),
			"item_name": item.get("item_name") or item_code,
			"comments": item.get("comment", item.get("comments", "")),
			"source_invoice_item": item.get("source_invoice_item") or item.get("name") or f"{item_code}:{index}",
		})
	return order_items


def _get_menu(invoice, branch):
	if invoice.restaurant_table:
		room = frappe.db.get_value("URY Table", invoice.restaurant_table, "restaurant_room")
		restaurant = frappe.db.get_value("URY Table", invoice.restaurant_table, "restaurant")
		return frappe.db.get_value("Menu for Room", {"room": room, "parent": restaurant}, "menu")
	return frappe.db.get_value("URY Restaurant", {"branch": branch}, "active_menu")


def _set_header_status(kot):
	active = sum(flt(row.active_quantity) for row in kot.kot_items)
	prepared = sum(min(flt(row.prepared_quantity), flt(row.active_quantity)) for row in kot.kot_items)
	if active <= 0:
		kot.order_status = "Cancelled"
	elif prepared <= 0:
		kot.order_status = "Ready For Prepare"
	elif prepared < active:
		kot.order_status = "Partially Prepared"
	else:
		kot.order_status = "Served"
	return kot.order_status


def _update_row_status(row):
	active = flt(row.active_quantity)
	prepared = min(flt(row.prepared_quantity), active)
	row.prepared_quantity = prepared
	if active <= 0:
		row.preparation_status = "Cancelled"
	elif prepared >= active:
		row.preparation_status = "Served"
	else:
		row.preparation_status = "Ready For Prepare"


def _publish_kot(kot):
	if hasattr(kot, "kotDisplayRealtime"):
		kot.kotDisplayRealtime()


def _sync_kot(invoice, current_items, comments, kot_naming_series):
	productions = get_production_units(invoice.pos_profile)
	if not productions:
		frappe.throw(_("Create a URY Production Unit against POS Profile: {0}").format(invoice.pos_profile))

	items = create_order_items(current_items)
	production_by_item = get_item_production_map(invoice.pos_profile, [row["item_code"] for row in items])
	items = [row for row in items if production_by_item.get(row["item_code"])]
	existing_names = frappe.get_all(
		"URY KOT",
		filters={"invoice_type": invoice.doctype, "invoice": invoice.name},
		pluck="name",
		order_by="creation",
	)
	# Historical multi-KOT orders remain untouched. New orders always have one lifecycle KOT.
	if len(existing_names) > 1:
		return None
	if not items and not existing_names:
		return None
	if existing_names:
		existing_doc = frappe.get_doc("URY KOT", existing_names[0])
		if existing_doc.kot_items and not any(row.source_invoice_item for row in existing_doc.kot_items):
			return None

	kot = existing_doc if existing_names else frappe.get_doc({
		"doctype": "URY KOT",
		"invoice_type": invoice.doctype,
		"invoice": invoice.name,
		"restaurant_table": invoice.restaurant_table,
		"customer_name": invoice.customer,
		"pos_profile": invoice.pos_profile,
		"comments": comments,
		"type": "New Order",
		"naming_series": kot_naming_series,
		"production": productions[0].name if len(productions) == 1 else None,
		"aggregator_id": invoice.get("custom_aggregator_id"),
		"is_aggregator": 1 if invoice.get("order_type") == "Aggregators" else 0,
		"order_no": invoice.get("custom_ury_order_number"),
	})

	branch = frappe.db.get_value("POS Profile", invoice.pos_profile, "branch")
	menu = _get_menu(invoice, branch)
	existing = {row.source_invoice_item: row for row in kot.kot_items if row.source_invoice_item}
	current_keys = set()
	for item in items:
		key = item["source_invoice_item"]
		current_keys.add(key)
		row = existing.get(key)
		if not row:
			row = kot.append("kot_items", {
				"item": item["item_code"],
				"item_name": item["item_name"],
				"source_invoice_item": key,
				"prepared_quantity": 0,
			})
		old_active = flt(row.active_quantity)
		new_active = max(flt(item["qty"]), 0)
		row.item = item["item_code"]
		row.item_name = item["item_name"]
		row.quantity = new_active
		row.active_quantity = new_active
		row.cancelled_qty = max(flt(row.cancelled_qty) + max(old_active - new_active, 0), 0)
		row.prepared_quantity = min(flt(row.prepared_quantity), new_active)
		row.comments = item["comments"]
		row.production_unit = production_by_item[item["item_code"]]
		row.course = frappe.db.get_value("URY Menu Item", {"item": item["item_code"], "parent": menu}, "course")
		_update_row_status(row)

	for row in kot.kot_items:
		if row.source_invoice_item and row.source_invoice_item not in current_keys:
			row.cancelled_qty = flt(row.cancelled_qty) + flt(row.active_quantity)
			row.active_quantity = 0
			row.prepared_quantity = 0
			_update_row_status(row)

	_set_header_status(kot)
	if kot.is_new():
		kot.insert()
		kot.submit()
	else:
		kot.type = "Order Modified"
		kot.flags.ignore_validate_update_after_submit = True
		kot.save(ignore_permissions=True)
		_publish_kot(kot)
		kot.create_or_update_work_orders()
	return kot


@frappe.whitelist()
def kot_execute(invoice_type, invoice_id, customer, restaurant_table=None, current_items=None, previous_items=None, comments=None):
	current_items = load_json(current_items or [])
	invoice = frappe.get_doc(invoice_type, invoice_id)
	pos_profile = frappe.get_doc("POS Profile", invoice.pos_profile)
	if not pos_profile.custom_kot_naming_series:
		frappe.throw(
			_("KOT Naming Series is mandatory for the auto creation of KOT. Ensure it is configured in POS Profile: {0}").format(pos_profile.name)
		)
	lock_name = f"ury_kot:{invoice_type}:{invoice_id}"
	with frappe.cache().lock(lock_name, timeout=30, blocking_timeout=10):
		return _sync_kot(invoice, current_items, comments, pos_profile.custom_kot_naming_series)


# Compatibility wrappers used by older server-side callers.
def process_items_for_kot(invoice_type, invoice_id, customer, restaurant_table, items, comments, pos_profile_id, kot_naming_series, kot_type):
	invoice = frappe.get_doc(invoice_type, invoice_id)
	return _sync_kot(invoice, items, comments, kot_naming_series)


def process_items_for_cancel_kot(invoice_type, invoice_id, customer, restaurant_table, items, comments, pos_profile_id, cancel_kot_naming_series, kot_type, invoiceItems):
	invoice = frappe.get_doc(invoice_type, invoice_id)
	return _sync_kot(invoice, invoice.items, comments, cancel_kot_naming_series.replace("CNCL-", "", 1))


def compare_two_array(array_1, array_2):
	previous = {row.get("source_invoice_item") or row["item_code"]: flt(row["qty"]) for row in array_2}
	return [{**row, "qty": flt(row["qty"]) - previous.get(row.get("source_invoice_item") or row["item_code"], 0)} for row in array_1 if flt(row["qty"]) != previous.get(row.get("source_invoice_item") or row["item_code"], 0)]


def get_removed_items(array_1, array_2):
	current = {row.get("source_invoice_item") or row["item_code"] for row in array_2}
	return [row for row in array_1 if (row.get("source_invoice_item") or row["item_code"]) not in current]
