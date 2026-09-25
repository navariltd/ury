import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from ury.ury.api.ury_kot_generate import _set_header_status, _update_row_status
from ury.ury.api.ury_kot_access import (
	assert_kot_access,
	get_authorized_production_unit,
)
from ury.ury.production_routing import get_production_units


def _unit_context(production_unit):
	unit = get_authorized_production_unit(production_unit)
	profile = frappe.db.get_value(
		"POS Profile", unit.pos_profile,
		["custom_kot_warning_time", "custom_kot_alert", "custom_reset_order_number_daily"], as_dict=True,
	) or frappe._dict()
	return unit, profile, get_production_units(unit.pos_profile)


def _station_rows(kot, production_unit, served=False):
	rows = []
	for row in kot.kot_items:
		if row.production_unit:
			if row.production_unit != production_unit:
				continue
			is_served = row.preparation_status == "Served" or (
				flt(row.active_quantity) > 0 and flt(row.prepared_quantity) >= flt(row.active_quantity)
			)
			if served != is_served:
				continue
		elif kot.production != production_unit:
			continue
		elif served != (kot.order_status == "Served"):
			continue
		rows.append(row)
	return rows


def _serialize_for_station(kot, production_unit, served=False):
	rows = _station_rows(kot, production_unit, served)
	if not rows:
		return None
	payload = json.loads(frappe.as_json(kot))
	payload["kot_items"] = [json.loads(frappe.as_json(row)) for row in rows]
	payload["production"] = production_unit
	return payload


def _list(production_unit, served=False):
	unit, profile, units = _unit_context(production_unit)
	three_hours_ago = frappe.utils.add_to_date(frappe.utils.now(), hours=-3)
	statuses = ["Partially Prepared", "Served"] if served else ["Ready For Prepare", "Partially Prepared"]
	names = frappe.get_list(
		"URY KOT",
		fields=["name"],
		filters={
			"pos_profile": unit.pos_profile,
			"order_status": ("in", statuses),
			"docstatus": 1,
			"verified": 0,
			"creation": (">=", three_hours_ago),
		},
		order_by="creation desc",
	)
	kots = []
	for value in names:
		payload = _serialize_for_station(frappe.get_doc("URY KOT", value.name), production_unit, served)
		if payload:
			kots.append(payload)
	return {
		"KOT": kots,
		"Branch": unit.branch,
		"production_units": [row.name for row in units],
		"pos_profile": unit.pos_profile,
		"kot_alert_time": profile.custom_kot_warning_time,
		"audio_alert": profile.custom_kot_alert,
		"daily_order_number": profile.custom_reset_order_number_daily,
	}


@frappe.whitelist()
def serve_kot(name, production_unit, item_rows, time=None):
	item_rows = frappe.parse_json(item_rows) if isinstance(item_rows, str) else item_rows
	item_rows = set(item_rows or [])
	if not item_rows:
		frappe.throw(_("Select at least one item to serve."))
	kot = frappe.get_doc("URY KOT", name)
	unit = get_authorized_production_unit(production_unit)
	assert_kot_access(kot)
	if kot.pos_profile != unit.pos_profile:
		frappe.throw(_("The selected KOT does not belong to this production unit."), frappe.PermissionError)
	selected = [row for row in kot.kot_items if row.name in item_rows]
	if len(selected) != len(item_rows):
		frappe.throw(_("One or more selected KOT items no longer exist."))
	if any((row.production_unit or kot.production) != production_unit for row in selected):
		frappe.throw(_("Selected items do not belong to production unit {0}.").format(production_unit))
	served_at = now_datetime()
	for row in selected:
		if flt(row.active_quantity) <= 0:
			continue
		row.prepared_quantity = row.active_quantity
		row.served_at = served_at
		row.served_by = frappe.session.user
		_update_row_status(row)
	status = _set_header_status(kot)
	if status == "Served":
		kot.start_time_serv = time or served_at
		kot.served_by = frappe.session.user
		kot.production_time = (get_datetime(served_at) - get_datetime(kot.creation)).total_seconds() / 60
	kot.flags.ignore_validate_update_after_submit = True
	kot.save(ignore_permissions=True)
	kot.kotDisplayRealtime()
	if status == "Served":
		from ury.ury.doctype.ury_kot.ury_kot import on_kot_update
		on_kot_update(kot, method=None)
	return {"name": kot.name, "order_status": status}


@frappe.whitelist()
def confirm_cancel_kot(name, user):
	kot = frappe.get_doc("URY KOT", name)
	assert_kot_access(kot)
	frappe.db.set_value(
		"URY KOT", name, {"verified": 1, "verified_by": frappe.session.user}
	)


@frappe.whitelist(allow_guest=True)
def get_site_name():
	return {"site_name": frappe.local.site}


@frappe.whitelist()
def kot_list(production_unit):
	return _list(production_unit, served=False)


@frappe.whitelist()
def served_kot_list(production_unit):
	return _list(production_unit, served=True)
