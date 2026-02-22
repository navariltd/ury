from datetime import datetime, timedelta

import frappe
from erpnext.accounts.doctype.pos_invoice.pos_invoice import (
    POSInvoice,
    get_stock_availability,
)
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from erpnext.stock.stock_ledger import is_negative_stock_allowed
from erpnext.stock.utils import get_stock_balance
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import flt, get_datetime, now


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
        self.auto_complete_work_orders()
        self.calculate_and_set_times()
        self.validate_invoice_print()
        self.ro_reload_submit()

    def on_trash(self):
        self.table_status_delete()

    def validate_stock_availablility(self):
        if self.is_return:
            return

        if self.docstatus.is_draft() and not frappe.db.get_value(
            "POS Profile", self.pos_profile, "validate_stock_on_save"
        ):
            return

        # Fetch QSR item groups for this POS Profile
        auto_manufacture_on_sale = self.get_auto_manufacture_setting()
        qsr_item_groups = self.get_qsr_item_groups(self.pos_profile)

        missing_materials = []

        for d in self.get("items"):
            if d.serial_and_batch_bundle:
                continue

            item_group = frappe.db.get_value("Item", d.item_code, "item_group")

            # If item belongs to QSR groups → validate raw materials
            if item_group in qsr_item_groups:
                if auto_manufacture_on_sale:
                    self.validate_qsr_raw_materials(
                        d, qsr_item_groups, missing_materials
                    )
                else:
                    self.validate_finished_item_stock(d)
            else:
                self.validate_normal_item_stock(d)

            self.raise_if_missing_materials(missing_materials)

        if (
            self.docstatus.is_draft()
            and qsr_item_groups
            and not self.skip_raw_material_validation
        ):
            self.skip_raw_material_validation = 1

    def get_auto_manufacture_setting(self):
        """Fetch Auto Manufacture on Sale flag from POS Profile"""
        return frappe.db.get_value(
            "POS Profile", self.pos_profile, "auto_manufacture_on_sale"
        )

    def validate_qsr_raw_materials(self, d, qsr_item_groups, missing_materials):
        """Validate that required raw materials for a QSR item are available."""
        if self.docstatus.is_draft() and not self.skip_raw_material_validation:
            bom = frappe.db.get_value(
                "BOM", {"item": d.item_code, "is_default": 1, "is_active": 1}, "name"
            )
            if not bom:
                frappe.throw(
                    _("Row #{0}: No default BOM found for QSR Item {1}").format(
                        d.idx, d.item_name
                    )
                )

            # Get raw materials from BOM
            leaf_items = self.get_all_leaf_bom_items(bom, self.company, qsr_item_groups)
            source_warehouse = frappe.db.get_value(
                "POS Profile", self.pos_profile, "warehouse"
            )

            for rm_code, rm in leaf_items.items():
                required_qty = flt(rm["qty"]) * flt(d.stock_qty)
                available_qty = get_stock_balance(
                    rm_code, source_warehouse, self.posting_date
                )

                if flt(available_qty) < required_qty:
                    missing_materials.append(
                        {
                            "row": d.idx,
                            "qsr_item": d.item_code,
                            "qsr_item_name": d.item_name,
                            "raw_material": rm_code,
                            "raw_material_name": rm["item_name"],
                            "required": required_qty,
                            "available": available_qty,
                        }
                    )

    def validate_finished_item_stock(self, d):
        """Validate available stock of a finished QSR item."""
        available_stock, is_stock_item = get_stock_availability(
            d.item_code, d.warehouse
        )
        if is_stock_item and flt(available_stock) < flt(d.stock_qty):
            frappe.throw(
                _(
                    "Row #{}: Insufficient stock for '{}'. Required: {}, Available: {} in warehouse '{}'."
                ).format(d.idx, d.item_name, d.stock_qty, available_stock, d.warehouse),
                title=_("Insufficient Stock"),
            )

    def validate_normal_item_stock(self, d):
        """Validate normal stock items not part of QSR groups."""
        available_stock, is_stock_item, is_negative_stock_allowed = get_stock_availability(
            d.item_code, d.warehouse
        )

        if is_negative_stock_allowed:
            return

        if is_stock_item and flt(available_stock) <= 0:
            frappe.throw(
                _("Row #{}: Item '{}' is out of stock in warehouse '{}'.").format(
                    d.idx, d.item_name, d.warehouse
                ),
                title=_("Item Unavailable"),
            )
        elif is_stock_item and flt(available_stock) < flt(d.stock_qty):
            frappe.throw(
                _(
                    "Row #{}: Insufficient stock for '{}'. Required: {}, Available: {} in warehouse '{}'."
                ).format(d.idx, d.item_name, d.stock_qty, available_stock, d.warehouse),
                title=_("Insufficient Stock"),
            )

    def raise_if_missing_materials(self, missing_materials):
        """Raise a single combined error message for missing raw materials."""
        if not missing_materials:
            return

        messages = ["Cannot process order - insufficient raw materials:"]
        for m in missing_materials:
            messages.append(
                _("• {} requires {} {} (only {} available)").format(
                    m["qsr_item_name"],
                    m["required"],
                    m["raw_material_name"],
                    m["available"],
                )
            )
        frappe.throw("\n".join(messages), title=_("Insufficient Raw Materials"))

    @staticmethod
    def get_all_leaf_bom_items(bom, company, qsr_item_groups):
        """
        Recursively expand a BOM into its ultimate raw materials ("leaf items").
        Respecting the "Do Not Explode" flag.

        - If a BOM item belongs to a QSR (make-to-order) group:
                - If it has "Do Not Explode" checked, treat as a leaf item.
                - Else, it it has a default BOM, recurse deeper,
                - If no default BOM exists, throw an error for misconfigured BOM.
        - If a BOM item is not in a QSR group:
                - Treat it directly as a leaf raw material.

        Quantities are aggregated and rounded using BOM Item precision.

        Example:
                Royal Breakfast: Spanish Omelette (QSR) - Eggs + Onions
                Final expansion: {Eggs, Onions, ...}
        """

        items = {}
        bom_items = get_bom_items_as_dict(bom, company=company)

        precision = get_field_precision(frappe.get_meta("BOM Item").get_field("qty"))

        for rm_code, rm in bom_items.items():
            rm_item_group = frappe.db.get_value("Item", rm_code, "item_group")

            do_not_explode = (
                frappe.db.get_value(
                    "BOM Item", {"parent": bom, "item_code": rm_code}, "do_not_explode"
                )
                or 0
            )

            if rm_item_group in qsr_item_groups and not do_not_explode:
                child_bom = frappe.db.get_value(
                    "BOM", {"item": rm_code, "is_default": 1, "is_active": 1}, "name"
                )
                if child_bom:
                    child_items = URYPOSInvoice.get_all_leaf_bom_items(
                        child_bom, company, qsr_item_groups
                    )
                    for code, child in child_items.items():
                        items[code] = items.get(
                            code, {"qty": 0, "item_name": child["item_name"]}
                        )
                        items[code]["qty"] = flt(
                            items[code]["qty"]
                            + (
                                flt(child["qty"], precision) * flt(rm["qty"], precision)
                            ),
                            precision,
                        )
                else:
                    # TODO: add a check for treating QSR without BOM as leaf/raw material
                    # No BOM found: treat QSR item as leaf
                    # items[rm_code] = items.get(rm_code, {"qty": 0, "item_name": rm["item_name"]})
                    # items[rm_code]["qty"] = flt(items[rm_code]["qty"] + flt(rm["qty"], precision), precision)
                    # QSR item expected to have BOM but none found: raise error
                    frappe.throw(
                        _(
                            f"Item {rm_code} is in a QSR group but has no default BOM. Please configure a BOM."
                        )
                    )
            else:
                # Either non-QSR or "Do Not Explode" = 1
                items[rm_code] = items.get(
                    rm_code, {"qty": 0, "item_name": rm["item_name"]}
                )
                items[rm_code]["qty"] = flt(
                    items[rm_code]["qty"] + flt(rm["qty"], precision), precision
                )

        return items

    def validate_invoice(self):
        if self.waiter is None or self.waiter == "":
            self.waiter = self.modified_by
        remove_items = frappe.db.get_value(
            "POS Profile", self.pos_profile, "remove_items"
        )

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
                if (
                    item_code in current_items
                    and current_items[item_code]["qty"] < item_data["qty"]
                ):
                    reduced_qty_items.append(
                        f"{item_data['name']} (qty reduced from {item_data['qty']} "
                        f"to {current_items[item_code]['qty']})"
                    )

            if removed_items or reduced_qty_items:
                error_msg = []
                if removed_items:
                    removed_item_names = [
                        original_items[item_code]["name"] for item_code in removed_items
                    ]
                    error_msg.append(f"Removed items: {', '.join(removed_item_names)}")
                if reduced_qty_items:
                    error_msg.append(
                        f"Modified quantities: {', '.join(reduced_qty_items)}"
                    )

                frappe.throw(
                    ("Cannot modify items after invoice is printed.\n{0}").format(
                        "\n".join(error_msg)
                    )
                )

    def validate_customer(self):
        if self.customer_name is None or self.customer_name == "":
            frappe.throw(("Failed to load data , Please Refresh the page "))

    def calculate_and_set_times(self):
        self.arrived_time = self.creation

        current_time_str = now()
        creation_time = None

        current_time = datetime.strptime(current_time_str, "%Y-%m-%d %H:%M:%S.%f")

        if isinstance(self.creation, str):
            creation_time = datetime.strptime(self.creation, "%Y-%m-%d %H:%M:%S.%f")
        else:
            creation_time = self.creation

        time_difference = current_time - creation_time

        total_seconds = int(time_difference.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        formatted_spend_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        self.total_spend_time = formatted_spend_time

    def validate_invoice_print(self):
        # Check if the invoice has been printed
        invoice_printed = frappe.db.get_value(
            "POS Invoice", self.name, "invoice_printed"
        )

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
                room = frappe.db.get_value(
                    "URY Table", self.restaurant_table, "restaurant_room"
                )
                menu_name = (
                    frappe.db.get_value(
                        "URY Restaurant", self.restaurant, "active_menu"
                    )
                    if not frappe.db.get_value(
                        "URY Restaurant", self.restaurant, "room_wise_menu"
                    )
                    else frappe.db.get_value(
                        "Menu for Room",
                        {"parent": self.restaurant, "room": room},
                        "menu",
                    )
                )

                self.selling_price_list = frappe.db.get_value(
                    "Price List", dict(restaurant_menu=menu_name, enabled=1)
                )

            if self.order_type == "Aggregators":
                price_list = frappe.db.get_value(
                    "Aggregator Settings",
                    {
                        "customer": self.customer,
                        "parent": self.branch,
                        "parenttype": "Branch",
                    },
                    "price_list",
                )

                if not price_list:
                    frappe.throw(
                        f"Price list for customer {self.customer} in branch {self.branch} not found in Aggregator Settings."
                    )

                self.selling_price_list = price_list

            else:
                menu_name = frappe.db.get_value(
                    "URY Restaurant", self.restaurant, "active_menu"
                )

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
            "URY Production Unit", {"pos_profile": pos_profile}, "name"
        )

        if not production_unit:
            return []

        return frappe.get_all(
            "URY Production Item Groups",
            filters={"parent": production_unit},
            pluck="item_group",
        )

    def auto_complete_work_orders(self):
        """
        Run before POS Invoice is submitted.
        - Ensures all linked Work Orders are submitted and completed.
        - For each WO:
            - If SE exists (draft) → submit it.
            - If SE exists (submitted) → skip.
            - Else → create and submit a new one.
        - Marks all related URY KOTs as Served.
        - Collects results and throws a single clear error summary if any failed.
        """

        if not self.get_auto_manufacture_setting():
            return

        failed, skipped, succeeded = [], [], []

        work_orders = frappe.get_all(
            "Work Order",
            filters={"invoice_type": "POS Invoice", "invoice": self.name},
            fields=["name", "status", "docstatus", "qty", "produced_qty"],
        )

        for wo in work_orders:
            work_order = frappe.get_doc("Work Order", wo.name)

            if work_order.docstatus == 0:
                work_order.submit()
                work_order.reload()

            pending_qty = (work_order.qty or 0) - (work_order.produced_qty or 0)

            if pending_qty <= 0 or work_order.status == "Completed":
                skipped.append(f"{wo.name} (already completed or no pending qty)")
                continue

            try:
                frappe.db.savepoint("before_auto_manufacture")

                existing_entries = frappe.get_all(
                    "Stock Entry",
                    filters={"work_order": work_order.name},
                    fields=["name", "docstatus"],
                    order_by="creation desc",
                    limit_page_length=1,
                )

                se_doc = None

                # Prefer a draft SE if it exists
                draft_entry = next(
                    (se for se in existing_entries if se.docstatus == 0), None
                )
                if draft_entry:
                    se_doc = frappe.get_doc("Stock Entry", draft_entry.name)
                    se_doc.submit()
                    succeeded.append(
                        f"{work_order.name} (used existing draft SE {se_doc.name})"
                    )

                # Otherwise, skip if already submitted
                elif existing_entries and existing_entries[0].docstatus == 1:
                    skipped.append(
                        f"{work_order.name} (SE {existing_entries[0].name} already submitted)"
                    )

                else:
                    # 2. Manufacture Stock Entry
                    stock_entry_data = make_stock_entry(
                        work_order.name, "Manufacture", qty=pending_qty
                    )

                    if not stock_entry_data:
                        failed.append(
                            (work_order.name, "make_stock_entry returned None")
                        )
                        frappe.db.rollback(save_point="before_auto_manufacture")
                        continue

                    stock_entry_doc = frappe.get_doc(
                        stock_entry_data
                    )  # Convert dict to Doc

                    # Align stock entry posting date/time with invoice
                    invoice_dt = get_datetime(
                        f"{self.posting_date} {self.posting_time}"
                    )
                    if invoice_dt.time().strftime("%H:%M:%S") == "00:00:00":
                        adjusted_dt = invoice_dt
                    else:
                        adjusted_dt = invoice_dt - timedelta(seconds=1)

                    invoice_dt = invoice_dt + timedelta(seconds=3)
                    self.posting_time = invoice_dt.time().strftime("%H:%M:%S")

                    stock_entry_doc.posting_date = adjusted_dt.date()
                    stock_entry_doc.posting_time = adjusted_dt.strftime("%H:%M:%S")

                    stock_entry_doc.flags.ignore_permissions = True
                    stock_entry_doc.insert()
                    stock_entry_doc.submit()
                    succeeded.append(
                        f"{work_order.name} (created new SE {stock_entry_doc.name})"
                    )

                if work_order.status != "Completed":
                    frappe.db.set_value(
                        "Work Order", work_order.name, "status", "Completed"
                    )
                    frappe.db.set_value(
                        "Work Order", work_order.name, "actual_end_date", now()
                    )

            except frappe.ValidationError as e:
                frappe.db.rollback(save_point="before_auto_manufacture")
                frappe.clear_messages()
                failed.append(f"{work_order.name}: insufficient stock → {e}")

            except Exception:
                frappe.db.rollback(save_point="before_auto_manufacture")
                failed.append(
                    f"{work_order.name}: unexpected error → {frappe.get_traceback()}"
                )

        def _mark_kot_served(kot_name):
            kot_doc = frappe.get_doc("URY KOT", kot_name)

            if kot_doc.order_status == "Served":
                return

            current_time = get_datetime()
            production_time = current_time - kot_doc.creation
            production_time_minutes = production_time.total_seconds() / 60

            kot_doc.start_time_serv = now()
            kot_doc.production_time = production_time_minutes
            kot_doc.order_status = "Served"

            kot_doc.save(ignore_permissions=True)

        kots = frappe.get_all(
            "URY KOT", filters={"invoice_type": "POS Invoice", "invoice": self.name}, fields=["name"]
        )

        for kot in kots:
            _mark_kot_served(kot["name"])

        frappe.db.commit()

        if failed:
            frappe.clear_messages()
            frappe.throw(
                "Some Work Orders could not be completed:\n\n" + "\n".join(failed),
                title="Auto Manufacture Errors",
            )
