import os

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.jinja import get_jenv
from frappe.utils.jinja_globals import bundled_asset
from pypdf import PdfWriter

no_cache = 1

base_template_path = "www/printview.html"
standard_format = "templates/print_formats/standard.html"


@frappe.whitelist()
def network_printing(
    doctype,
    name,
    printer_setting,
    print_format=None,
    doc=None,
    no_letterhead=0,
    file_path=None,
):
    try:
        print_settings = frappe.get_doc("Network Printer Settings", printer_setting)

        try:
            import cups
        except ImportError:
            return "Failed to import cups"

        try:
            cups.setServer(print_settings.server_ip)
            cups.setPort(print_settings.port)
            conn = cups.Connection()
        except Exception as e:
            return f"Failed to connect to the printer: {str(e)}"

        try:
            output = PdfWriter()
            output = frappe.get_print(
                doctype,
                name,
                print_format,
                doc=doc,
                no_letterhead=no_letterhead,
                as_pdf=True,
                output=output,
            )
            if not file_path:
                file_path = os.path.join(
                    "/", "tmp", f"frappe-pdf-{frappe.generate_hash()}.pdf"
                )

            with open(file_path, "wb") as f:
                output.write(f)
            conn.printFile(print_settings.printer_name, file_path, name, {})

            restaurant_table, invoice_printed, name = frappe.db.get_value(
                "POS Invoice", name, ["restaurant_table", "invoice_printed", "name"]
            )

            if restaurant_table and invoice_printed == 0:
                frappe.db.set_value("POS Invoice", name, "invoice_printed", 1)
                frappe.db.set_value(
                    "URY Table",
                    restaurant_table,
                    {"occupied": 0, "latest_invoice_time": None},
                )
            else:
                frappe.db.set_value("POS Invoice", name, "invoice_printed", 1)

            return "Success"
        except Exception as e:
            return f"Failed to print: {str(e)}"
    except Exception as e:
        import traceback

        traceback.print_exc()  # Print the full traceback for debugging
        return f"An error occurred: {str(e)}"


@frappe.whitelist()
def select_network_printer(pos_profile, invoice_id):
    table = frappe.db.get_value("POS Invoice", invoice_id, "restaurant_table")
    print_format = frappe.db.get_value("POS Profile", pos_profile, "print_format")

    if table:
        room = frappe.db.get_value("URY Table", table, "restaurant_room")
        room_bill_printer = frappe.db.get_value(
            "URY Printer Settings", {"parent": room, "bill": 1}, "printer"
        )
        if room_bill_printer:
            print = network_printing(
                "POS Invoice", invoice_id, room_bill_printer, print_format
            )
            return print

    else:
        pos_bill_printer = frappe.db.get_value(
            "URY Printer Settings", {"parent": pos_profile, "bill": 1}, "printer"
        )
        if pos_bill_printer:
            print = network_printing(
                "POS Invoice", invoice_id, pos_bill_printer, print_format
            )
            return print


@frappe.whitelist()
def qz_print_update(invoice):
    try:
        table = frappe.db.get_value("POS Invoice", invoice, "restaurant_table")

        if table is None or table == "":
            # Update invoice_printed
            frappe.db.set_value(
                "POS Invoice", invoice, "invoice_printed", 1, update_modified=False
            )

            # Validate the update
            new_invoice_printed = frappe.db.get_value(
                "POS Invoice", invoice, "invoice_printed"
            )
            if new_invoice_printed != 1:
                return {"status": "Failure"}
        else:
            invoice_printed = frappe.db.get_value(
                "POS Invoice", invoice, "invoice_printed"
            )

            if invoice_printed == 0:
                # Update invoice_printed
                frappe.db.set_value(
                    "POS Invoice", invoice, "invoice_printed", 1, update_modified=False
                )

                # Update table status
                frappe.db.set_value(
                    "URY Table", table, {"occupied": 0, "latest_invoice_time": None}
                )

                # Validate both updates
                new_invoice_printed = frappe.db.get_value(
                    "POS Invoice", invoice, "invoice_printed"
                )
                new_table_status = frappe.db.get_value("URY Table", table, "occupied")

                if new_invoice_printed != 1 or new_table_status != 0:
                    return {"status": "Failure"}

        return {"status": "Success"}

    except Exception as e:
        frappe.log_error(message=e, title="Print Fail")
        frappe.throw(_("Error while printing order", e))
        return {"status": "Failure"}


@frappe.whitelist()
def print_pos_page(doctype, name, print_format):
    data = {"name": name, "doctype": doctype, "print_format": print_format}

    restaurant_table, branch, name = frappe.db.get_value(
        "POS Invoice", name, ["restaurant_table", "branch", "name"]
    )
    print_channel = "{}_{}".format("print", branch)
    frappe.publish_realtime(print_channel, {"data": data})

    invoice_printed = frappe.db.get_value("POS Invoice", name, "invoice_printed")

    if invoice_printed == 0:
        frappe.db.set_value("POS Invoice", name, "invoice_printed", 1)

        if restaurant_table:
            frappe.db.set_value(
                "URY Table",
                restaurant_table,
                {"occupied": 0, "latest_invoice_time": None},
            )


@frappe.whitelist()
def qz_certificate():
    site_config = frappe.get_site_config()
    qz_key_value = site_config.get("qz_cert")

    return qz_key_value


@frappe.whitelist()
def signature_promise():
    site_config = frappe.get_site_config()
    key_value = site_config.get("qz_private_key")

    return key_value


def get_print_css():
    print_css = bundled_asset("print.bundle.css").lstrip("/")
    return frappe.read_file(os.path.join(frappe.local.sites_path, print_css))


@frappe.whitelist()
def print_pos_invoice(
    doctype: str,
    name: str,
    format_name: str = "POS Invoice",
    letter_head: str | None = None,
    no_letterhead: int = 0,
):
    """
    Safe API to return printable HTML for POS Invoice (including drafts)
    Performs permission checks and returns HTML to the client.
    """
    if not doctype or not name:
        frappe.throw(_("doctype and name are required"), exc=frappe.ValidationError)

    doc = frappe.get_doc(doctype, name)

    if not frappe.has_permission(doc=doc, ptype="read"):
        raise frappe.PermissionError(f"No read permission for {doctype} {name}")

    print_format = frappe.get_doc("Print Format", format_name)
    css = get_print_css()

    letterhead_html = ""
    if not cint(no_letterhead):
        if letter_head:
            letterhead_doc = frappe.get_doc("Letter Head", letter_head)
            letterhead_html = letterhead_doc.content or ""

    jenv = get_jenv()
    html = jenv.from_string(print_format.html or "").render(
        {
            "doc": doc,
            "no_letterhead": cint(no_letterhead),
            "letterhead": letterhead_html,
            "layout": "Print Format",
            "print_format": print_format,
        }
    )

    full_html = f"""\
        <html>
        <head>
            <meta charset="utf-8">
            <title>{frappe.utils.escape_html(doc.name)}</title>
            <style>{css}</style>
        </head>
        <body class="print-format">
            {letterhead_html}
            {html}
        </body>
        </html>
    """

    return full_html
