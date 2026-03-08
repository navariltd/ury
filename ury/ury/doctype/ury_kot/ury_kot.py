# Copyright (c) 2023, Tridz Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now, flt
from frappe.utils.print_format import print_by_server


class URYKOT(Document):
    def on_submit(self):
        self.multi_print_kot()
        self.kotDisplayRealtime()
        self.create_or_update_work_orders()

    def before_submit(self):
        self.userSetting()

    # Function for printing multiple KOTs.
    def multi_print_kot(self):
        # Function for printing a KOT on a specified printer using a print format.
        def print_kot(printer, kot_print_format):
            try:
                # Print KOT using a server function (print_by_server)
                print_by_server("URY KOT", self.name, printer, kot_print_format)
            except Exception:
                pass

        pos_kot_printers = frappe.db.get_all(
            "URY Printer Settings",
            fields=["printer", "kot_print_format", "kot_print"],
            filters={
                "parent": self.pos_profile,
                "kot_print": 1,
                "parenttype": "POS Profile",
            },
            order_by="idx",
        )

        pos_print_flag = True
        if self.production:
            production_unit_printers = frappe.get_all(
                "URY Printer Settings",
                fields=[
                    "printer",
                    "kot_print_format",
                    "kot_print",
                    "block_takeaway_kot",
                ],
                filters={
                    "parent": self.production,
                    "kot_print": 1,
                    "parenttype": "URY Production Unit",
                },
                order_by="idx",
            )

            # If production unit printer is specified, print KOT in production printer
            if production_unit_printers:
                for printer in production_unit_printers:
                    pos_print_flag = False
                    if printer.block_takeaway_kot == 1:
                        if self.restaurant_table and self.table_takeaway == 0:
                            print_kot(printer.printer, printer.kot_print_format)
                    else:
                        print_kot(printer.printer, printer.kot_print_format)

                # Check if restaurant table is specified and it's not a takeaway order
                if self.restaurant_table and self.table_takeaway == 0:
                    room = frappe.db.get_value(
                        "URY Table", self.restaurant_table, "restaurant_room"
                    )

                    room_kot_printers = frappe.get_all(
                        "URY Printer Settings",
                        fields=[
                            "printer",
                            "kot_print_format",
                            "kot_print",
                        ],
                        filters={
                            "parent": room,
                            "kot_print": 1,
                            "parenttype": "URY Room",
                        },
                        order_by="idx",
                    )

                    # If room printer is specified, print KOT in room
                    if room_kot_printers:
                        for printer in room_kot_printers:
                            pos_print_flag = False
                            print_kot(printer.printer, printer.kot_print_format)

                    if pos_print_flag:
                        if pos_kot_printers:
                            for printer in pos_kot_printers:
                                print_kot(
                                    printer.printer, printer.kot_print_format
                                )

                else:
                    if pos_kot_printers:
                        for printer in pos_kot_printers:
                            print_kot(printer.printer, printer.kot_print_format)

    # Function for displaying KOT-related information in real-time On KDS(Kitchen Display System)
    def kotDisplayRealtime(self):
        currentBranch = self.branch
        production = self.production
        kotjson = json.loads(frappe.as_json(self))
        audio_file = frappe.db.get_value(
            "POS Profile", self.pos_profile, "custom_kot_alert_sound"
        )
        cache_key = "{}_{}_last_kot_time".format(currentBranch, production)
        time = frappe.cache().get_value(cache_key)
        kot_channel = "{}_{}_{}".format("kot_update", currentBranch, production)
        frappe.publish_realtime(
            kot_channel,
            {"kot": kotjson, "audio_file": audio_file, "last_kot_time": time},
        )
        frappe.cache().set_value(cache_key, self.time)

    def userSetting(self):
        userDoc = frappe.get_doc("User", self.owner)
        self.user = userDoc.full_name

    def get_auto_manufacture_setting(self):
        """Fetch Auto Manufacture on Sale flag from POS Profile"""
        pos_profile = frappe.db.get_value(
            "URY Production Unit", self.production, "pos_profile"
        )
        return frappe.db.get_value(
            "POS Profile", pos_profile, "auto_manufacture_on_sale"
        )

    def create_or_update_work_orders(self):
        """
        Entry point: Synchronizes Work Orders based on URY KOTs for a given invoice.
        """

        auto_manufacture_on_sale = self.get_auto_manufacture_setting()
        if not auto_manufacture_on_sale:
            return

        company, fg_warehouse = frappe.db.get_value(
            "POS Profile", self.pos_profile, ["company", "warehouse"]
        )
        invoice_type = self.invoice_type
        invoice_id = self.invoice
        if not invoice_id or not invoice_type:
            frappe.throw(_("Cannot process Work Orders without an Invoice ID"))

        all_kots = get_all_kots(invoice_type, invoice_id)
        existing_wos = get_existing_work_orders(invoice_type, invoice_id)
        existing_map = {wo.production_item: wo for wo in existing_wos}

        item_totals = calculate_item_totals(all_kots)

        sync_work_orders(item_totals, existing_map, company, fg_warehouse, invoice_type, invoice_id)

        cleanup_obsolete_work_orders(item_totals, existing_map)


def get_all_kots(invoice_type, invoice_id):
    return frappe.get_all(
        "URY KOT",
        filters={"invoice_type": invoice_type, "invoice": invoice_id},
        fields=["name", "type", "original_kot"],
    )


def get_existing_work_orders(invoice_type, invoice_id):
    return frappe.get_all(
        "Work Order",
        filters={"invoice_type": invoice_type, "invoice": invoice_id},
        fields=["name", "production_item", "qty", "docstatus"],
    )


def calculate_item_totals(all_kots):
    """
    Computes total required quantities for each item based on KOTs.
    Handles partial cancellations too.
    """
    item_totals = {}

    for kot in all_kots:
        kot_doc = frappe.get_doc("URY KOT", kot.name)

        is_cancellation = kot_doc.type in ["Cancelled", "Partially cancelled"]

        for item in kot_doc.kot_items:
            item_code = item.item

            if is_cancellation:
                val = flt(item.cancelled_qty or item.quantity or 0)
            else:
                val = flt(item.quantity or 0)

            if item_code not in item_totals:
                item_totals[item_code] = 0.0

            if is_cancellation:
                item_totals[item_code] -= val
            else:
                item_totals[item_code] += val

    # Clean up: Ensure we don't return negative numbers if KOTs are messy
    for item in list(item_totals.keys()):
        if item_totals[item] <= 0:
            item_totals[item] = 0

    return item_totals


def sync_work_orders(item_totals, existing_map, company, fg_warehouse, invoice_type, invoice_id):
    """
    Creates or updates Work Orders based on calculated item totals.
    """
    for item_code, required_qty in item_totals.items():
        if required_qty <= 0:
            if item_code in existing_map:
                delete_or_cancel_wo(existing_map[item_code].name)
            continue


        default_bom = frappe.db.get_value("Item", item_code, "default_bom")
        if not default_bom:
            frappe.throw(_("No active default BOM found for {0}").format(item_code))

        if item_code in existing_map:
            wo = existing_map[item_code]
            if flt(wo.qty) != required_qty:
                wo_doc = frappe.get_doc("Work Order", wo.name)
                wo_doc.qty = required_qty
                wo_doc.set_work_order_operations()
                wo_doc.save()
        else:
            wo_doc = frappe.get_doc(
                {
                    "doctype": "Work Order",
                    "production_item": item_code,
                    "bom_no": default_bom,
                    "qty": required_qty,
                    "company": company,
                    "fg_warehouse": fg_warehouse,
                    "invoice_type": invoice_type,
                    "invoice": invoice_id,
                    "is_pos_manufacture": 1,
                }
            )
            wo_doc.insert()
            wo_doc.set_work_order_operations()
            wo_doc.flags.ignore_mandatory = True
            wo_doc.save()


def cleanup_obsolete_work_orders(item_totals, existing_map):
    """
    Deletes or cancels Work Orders for items no longer needed.
    """
    for item_code, wo in existing_map.items():
        if item_code not in item_totals or item_totals[item_code] <= 0:
            delete_or_cancel_wo(wo.name)


def delete_or_cancel_wo(wo_name):
    """
    Deletes Draft WOs, cancels Submitted WOs.
    """
    if not wo_name or not frappe.db.exists("Work Order", wo_name):
        return
    
    docstatus = frappe.db.get_value("Work Order", wo_name, "docstatus")

    if docstatus == 0:
        frappe.delete_doc("Work Order", wo_name, ignore_permissions=True)
    elif docstatus == 1:
        # wo_doc = frappe.get_doc("Work Order", wo_name)
        # wo_doc.cancel()
        pass


@frappe.whitelist()
def serve_kot(name, time):
    kot_doc = frappe.get_doc("URY KOT", name)

    current_time = get_datetime()
    production_time = current_time - kot_doc.creation
    production_time_minutes = production_time.total_seconds() / 60

    kot_doc.start_time_serv = time
    kot_doc.production_time = production_time_minutes
    kot_doc.order_status = "Served"

    on_kot_update(kot_doc, method=None)

    kot_doc.save(ignore_permissions=True)


def on_kot_update(doc, method):
    """
    Automatically completes Work Orders when a KOT's status becomes 'Served'.
    Uses the invoice to locate related Work Orders for accuracy.
    """

    if doc.order_status != "Served":
        return

    if not doc.invoice:
        return

    work_orders = frappe.get_all(
        "Work Order",
        filters={"invoice_type": doc.invoice_type, "invoice": doc.invoice},
        fields=["name", "status", "docstatus"],
    )

    if not work_orders:
        frappe.logger().info(
            f"No Work Orders found for invoice {doc.invoice_type} {doc.invoice} (KOT {doc.name})"
        )
        return

    for wo in work_orders:
        work_order = frappe.get_doc("Work Order", wo.name)

        if work_order.docstatus == 0:
            work_order.submit()
            work_order.reload()

        try:
            stock_entry_data = make_stock_entry(work_order.name, "Manufacture")
            if stock_entry_data:
                stock_entry_doc = frappe.get_doc(
                    stock_entry_data
                )  # Convert dict to Doc
                stock_entry_doc.insert()
                stock_entry_doc.submit()
                frappe.logger().info(
                    f"Stock Entry {stock_entry_doc.name} submitted for Work Order {wo.name}"
                )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Work Order Stock Entry Error for {wo.name}"
            )
            continue

        if work_order.status != "Completed":
            frappe.db.set_value("Work Order", work_order.name, "status", "Completed")
            frappe.db.set_value("Work Order", work_order.name, "actual_end_date", now())

    frappe.db.commit()
