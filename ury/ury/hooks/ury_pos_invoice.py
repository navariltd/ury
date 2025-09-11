from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt, now

from erpnext.accounts.doctype.pos_invoice.pos_invoice import POSInvoice, get_stock_availability


class URYPOSInvoice(POSInvoice):

	def before_insert(self):
		self.pos_invoice_naming()
		self.order_type_update()
		self.restrict_existing_order()


	def validate(self):
		super().validate()
		self.validate_invoice()
		self.validate_customer()
		self.validate_price_list()

		if self.taxes_and_charges and not len(self.get("taxes")):
			self.set_taxes()

		self.calculate_taxes_and_totals()


	def before_submit(self):
		self.calculate_and_set_times()
		self.validate_invoice_print()
		self.ro_reload_submit()


	def on_trash(self):
		self.table_status_delete()

	def validate_stock_availablility(self):
		from erpnext.stock.stock_ledger import is_negative_stock_allowed
		from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
		from erpnext.stock.utils import get_stock_balance

		if self.is_return:
			return

		if self.docstatus.is_draft() and not frappe.db.get_value(
			"POS Profile", self.pos_profile, "validate_stock_on_save"
		):
			return

		# Fetch QSR item groups for this POS Profile
		qsr_item_groups = self.get_qsr_item_groups(self.pos_profile)

		missing_materials = []

		for d in self.get("items"):
			if d.serial_and_batch_bundle:
				continue

			item_group = frappe.db.get_value("Item", d.item_code, "item_group")

			# If item belongs to QSR groups → validate raw materials
			if item_group in qsr_item_groups:
				# Find default BOM for the item
				bom = frappe.db.get_value("BOM", {"item": d.item_code, "is_default": 1}, "name")
				if not bom:
					frappe.throw(
						_("Row #{0}: No default BOM found for QSR Item {1}").format(
							d.idx, frappe.bold(d.item_code)
						)
					)

				# Get raw materials from BOM
				bom_items = get_bom_items_as_dict(bom, company=self.company)
				source_warehouse = frappe.db.get_value("POS Profile", self.pos_profile, "warehouse")

				for rm_code, rm in bom_items.items():
					required_qty = flt(rm["qty"]) * flt(d.stock_qty)
					available_qty = get_stock_balance(
						rm_code, source_warehouse, self.posting_date
					)

					if flt(available_qty) < required_qty:
						missing_materials.append(
							{
								"row": d.idx,
								"qsr_item": d.item_code,
								"raw_material": rm_code,
								"required": required_qty,
								"available": available_qty,
							}
						)

				continue  # Skip normal stock check for QSR items

			# Normal stock validation for non-QSR items
			if is_negative_stock_allowed(item_code=d.item_code):
				continue

			available_stock, is_stock_item = get_stock_availability(d.item_code, d.warehouse)
			item_code, warehouse = frappe.bold(d.item_code), frappe.bold(d.warehouse)

			if is_stock_item and flt(available_stock) <= 0:
				frappe.throw(
					_("Row #{}: Item Code {} is not available under warehouse {}.").format(
						d.idx, item_code, warehouse
					),
					title=_("Item Unavailable"),
				)
			elif is_stock_item and flt(available_stock) < flt(d.stock_qty):
				frappe.throw(
					_("Row #{}: Stock quantity not enough for Item Code {} under warehouse {}.").format(
						d.idx, item_code, warehouse
					),
					title=_("Item Unavailable"),
				)

		# After checking all items → show one combined error if any raw materials are missing
		if missing_materials:
			messages = []
			for m in missing_materials:
				messages.append(
					_("Row #{0} | QSR Item: <b>{1}</b> → Raw Material: <b>{2}</b> "
					"(Required: {3}, Available: {4})").format(
						m["row"], m["qsr_item"], m["raw_material"],
						m["required"], m["available"]
					)
				)
			frappe.throw(
				"<br>".join(messages),
				title=_("Insufficient Raw Materials")
			)


	def validate_invoice(self):
		if self.waiter == None or self.waiter == "":
			self.waiter = self.modified_by
		remove_items = frappe.db.get_value("POS Profile", self.pos_profile, "remove_items")
		
		if self.invoice_printed == 1 and remove_items == 0:
			# Get the original items from db
			original_doc = frappe.get_doc("POS Invoice", self.name)
			
			# Create dictionaries to store both quantities and names
			original_items = {
				item.item_code: {"qty": item.qty, "name": item.item_name} 
				for item in original_doc.items
			}
			current_items = {
				item.item_code: {"qty": item.qty, "name": item.item_name} 
				for item in self.items
			}
			
			# Check for removed items
			removed_items = set(original_items.keys()) - set(current_items.keys())
			
			# Check for quantity reductions
			reduced_qty_items = []
			for item_code, item_data in original_items.items():
				if (item_code in current_items and 
					current_items[item_code]["qty"] < item_data["qty"]):
					reduced_qty_items.append(
						f"{item_data['name']} (qty reduced from {item_data['qty']} "
						f"to {current_items[item_code]['qty']})"
					)
			
			if removed_items or reduced_qty_items:
				error_msg = []
				if removed_items:
					removed_item_names = [
						original_items[item_code]["name"] 
						for item_code in removed_items
					]
					error_msg.append(f"Removed items: {', '.join(removed_item_names)}")
				if reduced_qty_items:
					error_msg.append(f"Modified quantities: {', '.join(reduced_qty_items)}")
					
				frappe.throw(
					("Cannot modify items after invoice is printed.\n{0}")
					.format("\n".join(error_msg))
				)


	def validate_customer(self):
		if self.customer_name == None or self.customer_name == "":
			frappe.throw(
				(" Failed to load data , Please Refresh the page ").format(
					self.customer_name
				)
			)


	def calculate_and_set_times(self):
		self.arrived_time = self.creation

		current_time_str = now()
		
		current_time = datetime.strptime(current_time_str, "%Y-%m-%d %H:%M:%S.%f")
		
		time_difference = current_time - self.creation
		
		total_seconds = int(time_difference.total_seconds())
		hours, remainder = divmod(total_seconds, 3600)
		minutes, seconds = divmod(remainder, 60)
		
		formatted_spend_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
		self.total_spend_time = formatted_spend_time


	def validate_invoice_print(self):
		# Check if the invoice has been printed
		invoice_printed = frappe.db.get_value("POS Invoice", self.name, "invoice_printed")

		# If the invoice is associated with a restaurant table and hasn't been printed
		if self.restaurant_table and invoice_printed == 0:
			frappe.throw(
				"Printing the invoice is mandatory before submitting. Please print the invoice."
			)


	def table_status_delete(self):
		if self.restaurant_table:
			frappe.db.set_value(
				"URY Table",
				self.restaurant_table,
				{"occupied": 0, "latest_invoice_time": None},
			)


	def pos_invoice_naming(self):
		pos_profile = frappe.get_doc("POS Profile", self.pos_profile)
		restaurant = pos_profile.restaurant

		if not self.restaurant_table:
			self.naming_series = frappe.db.get_value(
				"URY Restaurant", restaurant, "invoice_series_prefix"
			)
			
			if self.order_type == "Aggregators":
				self.naming_series = frappe.db.get_value(
					"URY Restaurant", restaurant, "aggregator_series_prefix"
				)
	


	def order_type_update(self):
		if self.restaurant_table:
			if not self.order_type:
				is_take_away = frappe.db.get_value(
					"URY Table", self.restaurant_table, "is_take_away"
				)
				if is_take_away == 1:
					self.order_type = "Take Away"
				else:
					self.order_type = "Dine In"
	


	# reload restaurant order page if submitted invoice is open there
	def ro_reload_submit(self):
		frappe.publish_realtime("reload_ro", {"name": self.name})


	def validate_price_list(self):
			
		if self.restaurant:
			
			if self.restaurant_table:
				room = frappe.db.get_value("URY Table", self.restaurant_table, "restaurant_room")
				menu_name = (
					frappe.db.get_value("URY Restaurant", self.restaurant, "active_menu")
					if not frappe.db.get_value(
						"URY Restaurant", self.restaurant, "room_wise_menu"
					)
					else frappe.db.get_value(
						"Menu for Room", {"parent": self.restaurant, "room": room}, "menu"
					)
				)

				self.selling_price_list = frappe.db.get_value(
					"Price List", dict(restaurant_menu=menu_name, enabled=1)
				)
			
			if self.order_type == "Aggregators":
				price_list = frappe.db.get_value("Aggregator Settings",
					{"customer": self.customer, "parent": self.branch, "parenttype": "Branch"},
					"price_list",
					)
				
				if not price_list:
					frappe.throw(f"Price list for customer {self.customer} in branch {self.branch} not found in Aggregator Settings.")
					
				self.selling_price_list = price_list
				
			else:
				menu_name = frappe.db.get_value("URY Restaurant", self.restaurant, "active_menu") 

				self.selling_price_list = frappe.db.get_value(
					"Price List", dict(restaurant_menu=menu_name, enabled=1)
				)
			

	def restrict_existing_order(self):
		if self.restaurant_table:
			invoice_exist = frappe.db.exists(
				"POS Invoice",
				{
					"restaurant_table": self.restaurant_table,
					"docstatus": 0,
					"invoice_printed": 0,
				},
			)
			if invoice_exist:
				frappe.throw(
					("Table {0} has an existing invoice").format(self.restaurant_table)
				)

	@staticmethod
	def get_qsr_item_groups(pos_profile):
		"""
		Get all item groups linked to the URY Production Unit assigned to this POS Profile.
		"""
		production_unit = frappe.db.get_value(
			"URY Production Unit", {"pos_profile", pos_profile}, "name"
		)

		if not production_unit:
			return []
		
		return frappe.get_all(
			"URY Production Item Groups",
			filters={"parent": production_unit},
			pluck="item_group"
		)
