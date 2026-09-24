import frappe
from frappe.utils import flt


def execute():
	rows = frappe.get_all(
		"URY KOT Items",
		fields=["name", "parent", "quantity"],
		filters={"production_unit": ("is", "not set")},
	)
	for row in rows:
		kot = frappe.db.get_value(
			"URY KOT", row.parent, ["production", "order_status"], as_dict=True
		)
		if not kot or not kot.production:
			continue
		active = flt(row.quantity)
		prepared = active if kot.order_status == "Served" else 0
		frappe.db.set_value(
			"URY KOT Items",
			row.name,
			{
				"production_unit": kot.production,
				"active_quantity": active,
				"prepared_quantity": prepared,
				"preparation_status": "Served" if prepared else "Ready For Prepare",
			},
			update_modified=False,
		)
