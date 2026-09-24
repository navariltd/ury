import frappe
from frappe import _


def get_production_units(pos_profile):
	"""Return production units configured directly for a POS Profile."""
	if not pos_profile:
		return []
	return frappe.get_all(
		"URY Production Unit",
		filters={"pos_profile": pos_profile},
		fields=["name", "production", "branch", "warehouse"],
		order_by="creation, name",
	)


def get_production_item_group_map(pos_profile, validate=True):
	"""Map each QSR item group to its single production unit."""
	units = get_production_units(pos_profile)
	if not units:
		return {}
	rows = frappe.get_all(
		"URY Production Item Groups",
		filters={"parent": ("in", [unit.name for unit in units]), "parenttype": "URY Production Unit"},
		fields=["parent", "item_group"],
		order_by="parent, idx",
	)
	routing = {}
	conflicts = {}
	for row in rows:
		if row.item_group in routing and routing[row.item_group] != row.parent:
			conflicts.setdefault(row.item_group, {routing[row.item_group]}).add(row.parent)
		else:
			routing[row.item_group] = row.parent
	if conflicts and validate:
		details = "; ".join(
			_("{0}: {1}").format(group, ", ".join(sorted(parents)))
			for group, parents in sorted(conflicts.items())
		)
		frappe.throw(
			_("An item group can belong to only one production unit per POS Profile. Conflicts: {0}").format(details)
		)
	return routing


def get_qsr_item_groups(pos_profile):
	return list(get_production_item_group_map(pos_profile))


def get_item_production_map(pos_profile, item_codes):
	routing = get_production_item_group_map(pos_profile)
	item_codes = list({code for code in item_codes if code})
	if not item_codes:
		return {}
	groups = dict(frappe.get_all(
		"Item", filters={"name": ("in", item_codes)},
		fields=["name", "item_group"], as_list=True,
	))
	return {code: routing.get(groups.get(code)) for code in item_codes}
