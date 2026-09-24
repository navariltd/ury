import frappe
from erpnext.accounts.doctype.pos_invoice.pos_invoice import get_stock_availability
from frappe import _
from frappe.utils import flt


class URYInvoiceStockMixin:
	def validate_finished_item_stock(self, item):
		"""Validate available stock of a finished QSR item."""
		available_stock, is_stock_item, is_negative_stock_allowed = get_stock_availability(
			item.item_code, item.warehouse
		)

		if is_negative_stock_allowed:
			return

		if is_stock_item and flt(available_stock) < flt(item.stock_qty):
			frappe.throw(
				_(
					"Row #{}: Insufficient stock for '{}'. Required: {}, Available: {} in warehouse '{}'."
				).format(
					item.idx,
					item.item_name,
					item.stock_qty,
					available_stock,
					item.warehouse,
				),
				title=_("Insufficient Stock"),
			)

	def validate_normal_item_stock(self, item):
		"""Validate normal stock items not part of QSR groups."""
		available_stock, is_stock_item, is_negative_stock_allowed = get_stock_availability(
			item.item_code, item.warehouse
		)

		if is_negative_stock_allowed:
			return

		if is_stock_item and flt(available_stock) <= 0:
			frappe.throw(
				_("Row #{}: Item '{}' is out of stock in warehouse '{}'.").format(
					item.idx, item.item_name, item.warehouse
				),
				title=_("Item Unavailable"),
			)
		elif is_stock_item and flt(available_stock) < flt(item.stock_qty):
			frappe.throw(
				_(
					"Row #{}: Insufficient stock for '{}'. Required: {}, Available: {} in warehouse '{}'."
				).format(
					item.idx,
					item.item_name,
					item.stock_qty,
					available_stock,
					item.warehouse,
				),
				title=_("Insufficient Stock"),
			)
