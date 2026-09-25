import frappe
from frappe import _


def assert_pos_profile_access(pos_profile):
	"""Require explicit POS Profile assignment for every non-Administrator user."""
	user = frappe.session.user
	if user == "Administrator":
		return
	if user == "Guest" or not frappe.db.exists(
		"POS Profile User",
		{
			"parent": pos_profile,
			"parenttype": "POS Profile",
			"parentfield": "applicable_for_users",
			"user": user,
		},
	):
		frappe.throw(
			_("You are not permitted to access this Kitchen Display System."),
			frappe.PermissionError,
		)


def get_authorized_production_unit(production_unit):
	unit = frappe.db.get_value(
		"URY Production Unit",
		production_unit,
		["name", "pos_profile", "branch"],
		as_dict=True,
	)
	if not unit:
		frappe.throw(_("Unknown production unit."))
	assert_pos_profile_access(unit.pos_profile)
	return unit


def assert_kot_access(kot):
	assert_pos_profile_access(kot.pos_profile)
	return kot.pos_profile


def _first_production_unit(pos_profiles):
	for pos_profile in pos_profiles:
		production_unit = frappe.db.get_value(
			"URY Production Unit",
			{"pos_profile": pos_profile},
			"name",
			order_by="creation, name",
		)
		if production_unit:
			return production_unit
	return None


def _session_full_name():
	return (
		frappe.db.get_value("User", frappe.session.user, "full_name")
		or frappe.session.user
	)


@frappe.whitelist()
def get_kds_context(production_unit=None):
	"""Resolve the requested display or a deterministic display assigned to the user."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to access the Kitchen Display System."), frappe.PermissionError)
	requested = frappe.db.get_value(
		"URY Production Unit",
		production_unit,
		["name", "pos_profile"],
		as_dict=True,
	) if production_unit else None
	if production_unit and not requested:
		frappe.throw(_("Unknown production unit."))

	if frappe.session.user == "Administrator":
		selected = requested.name if requested else frappe.db.get_value(
			"URY Production Unit", {}, "name", order_by="creation, name"
		)
		return {
			"authorized": bool(selected),
			"production_unit": selected,
			"requested_pos_profile": requested.pos_profile if requested else None,
			"user_full_name": _session_full_name(),
		}

	assignments = frappe.get_all(
		"POS Profile User",
		filters={
			"parenttype": "POS Profile",
			"parentfield": "applicable_for_users",
			"user": frappe.session.user,
		},
		fields=["parent", "default", "idx"],
		order_by="default desc, idx asc",
	)
	assigned_profiles = list(dict.fromkeys(row.parent for row in assignments))
	if requested and requested.pos_profile in assigned_profiles:
		return {
			"authorized": True,
			"production_unit": requested.name,
			"requested_pos_profile": requested.pos_profile,
			"user_full_name": _session_full_name(),
		}

	fallback = _first_production_unit(assigned_profiles)
	return {
		"authorized": False,
		"production_unit": fallback,
		"requested_pos_profile": requested.pos_profile if requested else None,
		"user_full_name": _session_full_name(),
	}
