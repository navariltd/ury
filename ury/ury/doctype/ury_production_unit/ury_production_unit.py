# Copyright (c) 2023, Tridz Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class URYProductionUnit(Document):
	def validate(self):
		if not self.pos_profile:
			return
		groups = [row.item_group for row in self.item_groups if row.item_group]
		if len(groups) != len(set(groups)):
			frappe.throw(_("An item group cannot be repeated in the same production unit."))
		conflicts = frappe.get_all(
			"URY Production Item Groups",
			filters={"item_group": ("in", groups), "parent": ("!=", self.name), "parenttype": "URY Production Unit"},
			fields=["parent", "item_group"],
		) if groups else []
		conflicts = [row for row in conflicts if frappe.db.get_value("URY Production Unit", row.parent, "pos_profile") == self.pos_profile]
		if conflicts:
			details = "; ".join(f"{row.item_group}: {row.parent}" for row in conflicts)
			frappe.throw(_("Item groups are already assigned to another production unit on this POS Profile: {0}").format(details))
