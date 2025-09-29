import json
from datetime import date, datetime, timedelta


import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import (
    make_closing_entry_from_opening,
    get_pos_invoices
)


@frappe.whitelist()
def getTable(room):
    branch_name = getBranch()
    tables = frappe.get_all(
        "URY Table",
        fields=[
            "name",
            "occupied",
            "latest_invoice_time",
            "is_take_away",
            "restaurant_room",
            "table_shape",
        ],
        filters={
            "branch": branch_name,
            "restaurant_room": room,
        },
    )
    return tables


@frappe.whitelist()
def getRestaurantMenu(pos_profile, room=None, order_type=None):
    menu_items = []
    menu_items_with_image = []

    user_role = frappe.get_roles()

    pos_profile = frappe.get_doc("POS Profile", pos_profile)

    cashier = any(
        role.role in user_role for role in pos_profile.role_allowed_for_billing
    )
    branch_name = getBranch()
    restaurant = frappe.db.get_value("URY Restaurant", {"branch": branch_name}, "name")

    if cashier and order_type:
        order_type_wise_menu = frappe.db.get_value(
            "URY Restaurant", restaurant, "order_type_wise_menu"
        )

        if order_type_wise_menu:
            menu = frappe.db.get_value(
                "Order Type Menu",
                {"parent": restaurant, "order_type": order_type},
                "menu",
            )
            if not menu:
                menu = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")

        else:
            menu = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")

    elif room:

        room_wise_menu = frappe.db.get_value(
            "URY Restaurant", restaurant, "room_wise_menu"
        )

        if room_wise_menu:
            menu = frappe.db.get_value(
                "Menu for Room", {"parent": restaurant, "room": room}, "menu"
            )
            if not menu:
                menu = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")
        else:
            menu = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")

    # Default menu if nothing is selected
    else:
        menu = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")

    if not menu:
        frappe.throw(
            _("Please set an active menu for Restaurant {0}").format(restaurant)
        )

    # Get menu items (your existing code)
    menu_items = frappe.get_all(
        "URY Menu Item",
        filters={"parent": menu, "disabled": 0},
        fields=["item", "item_name", "rate", "special_dish", "disabled", "course"],
        order_by="item_name asc",
    )

    menu_items_with_image = [
        {
            "item": item.item,
            "item_name": item.item_name,
            "rate": item.rate,
            "special_dish": item.special_dish,
            "disabled": item.disabled,
            "item_image": frappe.db.get_value("Item", item.item, "image"),
            "course": item.course,
        }
        for item in menu_items
    ]
    modified = frappe.db.get_value("URY Menu", menu, "modified")

    return {"items": menu_items_with_image, "modified_time": modified, "name": menu}


@frappe.whitelist()
def getBranch():
    user = frappe.session.user
    if user != "Administrator":
        sql_query = """
            SELECT b.branch
            FROM `tabURY User` AS a
            INNER JOIN `tabBranch` AS b ON a.parent = b.name
            WHERE a.user = %s
        """
        branch_array = frappe.db.sql(sql_query, user, as_dict=True)
        if not branch_array:
            frappe.throw("User is not Associated with any Branch.Please refresh Page")

        branch_name = branch_array[0].get("branch")

        return branch_name


@frappe.whitelist()
def getBranchRoom():
    user = frappe.session.user
    if user != "Administrator":
        sql_query = """
            SELECT b.branch , a.room
            FROM `tabURY User` AS a
            INNER JOIN `tabBranch` AS b ON a.parent = b.name
            WHERE a.user = %s
        """
        branch_array = frappe.db.sql(sql_query, user, as_dict=True)

        branch_name = branch_array[0].get("branch")
        room_name = branch_array[0].get("room")

        if not branch_name:
            frappe.throw(
                "Branch information is missing for the user. Please contact your administrator."
            )

        if not room_name:
            frappe.throw(
                "No room assigned to this user. Please contact your administrator."
            )

        return [
            {
                "name": room_name,
                "branch": branch_name,
            }
        ]


@frappe.whitelist()
def getRoom():
    user = frappe.session.user
    if user != "Administrator":
        sql_query = """
            SELECT b.branch, a.room
            FROM `tabURY User` AS a
            INNER JOIN `tabBranch` AS b ON a.parent = b.name
            WHERE a.user = %s
        """
        branch_array = frappe.db.sql(sql_query, user, as_dict=True)

        if not branch_array:
            frappe.throw(
                "No branch or room information found for the user. Please contact your administrator."
            )

        room_details = [
            {"name": row.get("room"), "branch": row.get("branch")}
            for row in branch_array
        ]

        return room_details


@frappe.whitelist()
def getModeOfPayment():
    posDetails = getPosProfile()
    posProfile = posDetails["pos_profile"]
    posProfiles = frappe.get_doc("POS Profile", posProfile)
    mode_of_payments = posProfiles.payments
    modeOfPayments = []
    for mop in mode_of_payments:
        modeOfPayments.append(
            {"mode_of_payment": mop.mode_of_payment, "opening_amount": float(0)}
        )
    return modeOfPayments


@frappe.whitelist()
def getInvoiceForCashier(status, cashier, limit, limit_start):
    branch = getBranch()
    updatedlist = []
    limit = int(limit) + 1
    limit_start = int(limit_start)
    if status == "Draft":
        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number, 
                pi.posting_date, pi.rounded_total, pi.order_type 
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s AND pi.cashier = %s
            AND (pi.invoice_printed = 1 OR (pi.invoice_printed = 0 AND COALESCE(pi.restaurant_table, '') = ''))
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, status, cashier, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    elif status == "Unbilled":

        docstatus = "Draft"
        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number, 
                pi.posting_date, pi.rounded_total, pi.order_type 
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s AND pi.cashier = %s
            AND (pi.invoice_printed = 0 AND pi.restaurant_table IS NOT NULL)
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, docstatus, cashier, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    elif status == "Recently Paid":
        docstatus = "Paid"
        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number,
                pi.posting_date, pi.rounded_total, pi.order_type, pi.additional_discount_percentage, pi.discount_amount 
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s AND pi.cashier = %s
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, docstatus, cashier, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    else:

        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number,
                pi.posting_date, pi.rounded_total, pi.order_type, pi.additional_discount_percentage, pi.discount_amount
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s AND pi.cashier = %s
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, status, cashier, limit, limit_start),
            as_dict=True,
        )

        updatedlist.extend(invoices)
    if len(updatedlist) == limit and status != "Recently Paid":
        next = True
        updatedlist.pop()
    else:
        next = False
    return {"data": updatedlist, "next": next}


@frappe.whitelist()
def getPosInvoice(status, limit, limit_start):
    branch = getBranch()
    updatedlist = []
    limit = int(limit) + 1
    limit_start = int(limit_start)
    if status == "Draft":
        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number, 
                pi.posting_date, pi.rounded_total, pi.order_type 
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s 
            AND (pi.invoice_printed = 1 OR (pi.invoice_printed = 0 AND COALESCE(pi.restaurant_table, '') = ''))
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, status, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    elif status == "Unbilled":

        docstatus = "Draft"
        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number, 
                pi.posting_date, pi.rounded_total, pi.order_type 
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s 
            AND (pi.invoice_printed = 0 AND pi.restaurant_table IS NOT NULL)
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, docstatus, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    elif status == "Recently Paid":
        docstatus = "Paid"
        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number,
                pi.posting_date, pi.rounded_total, pi.order_type, pi.additional_discount_percentage, pi.discount_amount 
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s 
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, docstatus, limit, limit_start),
            as_dict=True,
        )
        updatedlist.extend(invoices)
    else:

        invoices = frappe.db.sql(
            """
            SELECT 
                pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
                pi.cashier, u.full_name as cashier_name, pi.waiter, pi.net_total, pi.posting_time, 
                pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number,
                pi.posting_date, pi.rounded_total, pi.order_type, pi.additional_discount_percentage, pi.discount_amount
            FROM `tabPOS Invoice` pi
            LEFT JOIN `tabUser` u ON pi.cashier = u.email
            WHERE pi.branch = %s AND pi.status = %s 
            ORDER BY pi.modified desc
            LIMIT %s OFFSET %s
            """,
            (branch, status, limit, limit_start),
            as_dict=True,
        )

        updatedlist.extend(invoices)
    if len(updatedlist) == limit and status != "Recently Paid":
        next = True
        updatedlist.pop()
    else:
        next = False
    return {"data": updatedlist, "next": next}


@frappe.whitelist()
def searchPosInvoice(query, status):
    if not query:
        return {"data": [], "next": False}
    query = query.lower()

    # Build the WHERE clause based on status
    status_condition = ""
    if status == "Recently Paid":
        status_condition = "pi.status = 'Paid'"
    elif status == "Unbilled":
        status_condition = """pi.status = 'Draft' 
        AND pi.restaurant_table IS NOT NULL 
        AND pi.restaurant_table != '' 
        AND pi.invoice_printed = 0"""
    else:
        status_condition = f"pi.status = '{status}'"

    # Use SQL query to get orders with cashier full name
    pos_invoices = frappe.db.sql(
        f"""
        SELECT 
            pi.name, pi.customer, pi.grand_total, pi.posting_date, pi.posting_time,
            pi.order_type, pi.restaurant_table, pi.status, pi.rounded_total, 
            pi.net_total, pi.mobile_number, pi.cashier, u.full_name as cashier_name
        FROM `tabPOS Invoice` pi
        LEFT JOIN `tabUser` u ON pi.cashier = u.email
        WHERE ({status_condition})
        AND (
            LOWER(pi.name) LIKE %s 
            OR LOWER(pi.customer) LIKE %s 
            OR LOWER(pi.mobile_number) LIKE %s
        )
        ORDER BY pi.modified desc
        LIMIT 10
        """,
        (f"%{query}%", f"%{query}%", f"%{query}%"),
        as_dict=True,
    )

    return {"data": pos_invoices, "next": len(pos_invoices) == 10}


@frappe.whitelist()
def get_select_field_options():
    options = frappe.get_meta("POS Invoice").get_field("order_type").options
    if options:
        return [{"name": option} for option in options.split("\n")]
    else:
        return []


@frappe.whitelist()
def fav_items(customer):
    pos_invoices = frappe.get_all(
        "POS Invoice", filters={"customer": customer}, fields=["name"]
    )
    item_qty = {}

    for invoice in pos_invoices:
        pos_invoice = frappe.get_doc("POS Invoice", invoice.name)
        for item in pos_invoice.items:
            item_name = item.item_name
            qty = item.qty
            if item_name not in item_qty:
                item_qty[item_name] = 0
            item_qty[item_name] += qty

    favorite_items = [
        {"item_name": item_name, "qty": qty} for item_name, qty in item_qty.items()
    ]
    return favorite_items


@frappe.whitelist()
def getCashier(room):
    branch = getBranch()
    cashier = None
    pos_opening_list = frappe.db.sql(
        """
        SELECT DISTINCT `tabPOS Opening Entry`.name 
        FROM `tabPOS Opening Entry`
        INNER JOIN `tabMultiple Rooms` 
        ON `tabMultiple Rooms`.parent = `tabPOS Opening Entry`.name
        WHERE `tabPOS Opening Entry`.branch = %s
        AND `tabPOS Opening Entry`.status = 'Open'
        AND `tabPOS Opening Entry`.docstatus = 1
        AND `tabMultiple Rooms`.room = %s
    """,
        (branch, room),
        as_dict=True,
    )
    if pos_opening_list:
        cashier = frappe.db.get_value(
            "POS Opening Entry",
            {"name": pos_opening_list[0].name},
            "user",
        )
    return cashier


@frappe.whitelist()
def getPosProfile():
    branchName = getBranch()
    waiter = frappe.session.user
    bill_present = False
    qz_host = None
    printer = None
    cashier = None
    owner = None
    posProfile = frappe.db.exists("POS Profile", {"branch": branchName})
    pos_profiles = frappe.get_doc("POS Profile", posProfile)
    global_defaults = frappe.get_single("Global Defaults")
    disable_rounded_total = global_defaults.disable_rounded_total

    if pos_profiles.branch == branchName:
        pos_profile_name = pos_profiles.name
        warehouse = pos_profiles.warehouse
        branch = pos_profiles.branch
        company = pos_profiles.company
        tableAttention = pos_profiles.table_attention_time
        get_cashier = frappe.get_doc("POS Profile", pos_profile_name)
        print_format = pos_profiles.print_format
        paid_limit = pos_profiles.paid_limit
        enable_discount = pos_profiles.custom_enable_discount
        multiple_cashier = pos_profiles.custom_enable_multiple_cashier
        edit_order_type = pos_profiles.custom_edit_order_type
        enable_kot_reprint = pos_profiles.custom_enable_kot_reprint
        if multiple_cashier:
            details = getBranchRoom()
            room = details[0].get("name")
            branch = details[0].get("branch")

            pos_opening_list = frappe.db.sql(
                """
                SELECT DISTINCT `tabPOS Opening Entry`.name 
                FROM `tabPOS Opening Entry`
                INNER JOIN `tabMultiple Rooms` 
                ON `tabMultiple Rooms`.parent = `tabPOS Opening Entry`.name
                WHERE `tabPOS Opening Entry`.branch = %s
                AND `tabPOS Opening Entry`.status = 'Open'
                AND `tabPOS Opening Entry`.docstatus = 1
                AND `tabMultiple Rooms`.room = %s
            """,
                (branch, room),
                as_dict=True,
            )
            if pos_opening_list:
                pos_opened_cashier = frappe.db.get_value(
                    "POS Opening Entry",
                    {"name": pos_opening_list[0].name},
                    "user",
                )
            else:
                pos_opened_cashier = None
            for user_details in get_cashier.applicable_for_users:
                if user_details.custom_main_cashier:
                    owner = user_details.user

                if frappe.session.user == owner:
                    cashier = owner
                else:
                    cashier = pos_opened_cashier

        else:
            cashier = get_cashier.applicable_for_users[0].user
            owner = get_cashier.applicable_for_users[0].user

        qz_print = pos_profiles.qz_print
        print_type = None

        for pos_profile in pos_profiles.printer_settings:
            if pos_profile.bill == 1:
                printer = pos_profile.printer
                bill_present = True
                break

        if qz_print == 1:
            print_type = "qz"
            qz_host = pos_profiles.qz_host

        elif bill_present == True:
            print_type = "network"

        else:
            print_type = "socket"

    invoice_details = {
        "pos_profile": pos_profile_name,
        "branch": branch,
        "company": company,
        "waiter": waiter,
        "warehouse": warehouse,
        "cashier": cashier,
        "print_format": print_format,
        "qz_print": qz_print,
        "qz_host": qz_host,
        "printer": printer,
        "print_type": print_type,
        "tableAttention": tableAttention,
        "paid_limit": paid_limit,
        "disable_rounded_total": disable_rounded_total,
        "enable_discount": enable_discount,
        "multiple_cashier": multiple_cashier,
        "owner": owner,
        "edit_order_type": edit_order_type,
        "enable_kot_reprint": enable_kot_reprint,
    }

    return invoice_details


@frappe.whitelist()
def getPosInvoiceItems(invoice):
    itemDetails = []
    taxDetails = []
    orderdItems = frappe.get_doc("POS Invoice", invoice)
    posItems = orderdItems.items
    for items in posItems:
        item_name = items.item_name
        qty = items.qty
        amount = items.rate
        itemDetails.append(
            {
                "item_name": item_name,
                "qty": qty,
                "amount": amount,
            }
        )
    taxDetail = orderdItems.taxes
    for tax in taxDetail:
        description = tax.description
        rate = tax.tax_amount
        taxDetails.append(
            {
                "description": description,
                "rate": rate,
            }
        )
    return itemDetails, taxDetails


@frappe.whitelist()
def posOpening():
    branchName = getBranch()
    pos_opening_list = frappe.get_all(
        "POS Opening Entry",
        fields=["name", "docstatus", "status", "posting_date"],
        filters={"branch": branchName, "status": "Open", "docstatus": 1, "user": frappe.session.user},
    )
    print(pos_opening_list)
    if not pos_opening_list:
        return {
            "status": "not_opened",
            "opening_entry": None
        }
    
    return {
        "status": "open",
        "opening_entry": pos_opening_list[0].name
    }


@frappe.whitelist()
def getAggregator():
    branchName = getBranch()
    aggregatorList = frappe.get_all(
        "Aggregator Settings",
        fields=["customer"],
        filters={"parent": branchName, "parenttype": "Branch"},
    )
    return aggregatorList


@frappe.whitelist()
def getAggregatorItem(aggregator):
    branchName = getBranch()
    aggregatorItem = []
    aggregatorItemList = []
    priceList = frappe.db.get_value(
        "Aggregator Settings",
        {"customer": aggregator, "parent": branchName, "parenttype": "Branch"},
        "price_list",
    )
    aggregatorItem = frappe.get_all(
        "Item Price",
        fields=["item_code", "item_name", "price_list_rate"],
        filters={"selling": 1, "price_list": priceList},
    )
    aggregatorItemList = [
        {
            "item": item.item_code,
            "item_name": item.item_name,
            "rate": item.price_list_rate,
            "item_image": frappe.db.get_value("Item", item.item, "image"),
        }
        for item in aggregatorItem
        if not frappe.db.get_value("Item", item.item_code, "disabled")
    ]
    return aggregatorItemList


@frappe.whitelist()
def getAggregatorMOP(aggregator):
    branchName = getBranch()

    modeOfPayment = frappe.db.get_value(
        "Aggregator Settings",
        {"customer": aggregator, "parent": branchName, "parenttype": "Branch"},
        "mode_of_payments",
    )
    modeOfPaymentsList = []
    modeOfPaymentsList.append(
        {"mode_of_payment": modeOfPayment, "opening_amount": float(0)}
    )
    return modeOfPaymentsList


@frappe.whitelist()
def validate_pos_close(pos_profile):
    enable_unclosed_pos_check = frappe.db.get_value(
        "POS Profile", pos_profile, "custom_daily_pos_close"
    )

    if enable_unclosed_pos_check:
        current_datetime = frappe.utils.now_datetime()
        start_of_day = current_datetime.replace(
            hour=5, minute=0, second=0, microsecond=0
        )

        if current_datetime > start_of_day:
            previous_day = start_of_day - timedelta(days=1)

        else:
            previous_day = start_of_day

        unclosed_pos_opening = frappe.db.exists(
            "POS Opening Entry",
            {
                "posting_date": previous_day.date(),
                "status": "Open",
                "pos_profile": pos_profile,
                "docstatus": 1,
                "user": frappe.session.user,
            },
        )

        if unclosed_pos_opening:
            return "Failed"

        return "Success"

    return "Success"


@frappe.whitelist()
def getAllOrders(limit, limit_start):
    """Fetch all orders that are either Draft or Draft with Dine In order type"""
    branch = getBranch()
    updatedlist = []
    limit = int(limit) + 1
    limit_start = int(limit_start)

    invoices = frappe.db.sql(
        """
        SELECT 
            pi.name, pi.invoice_printed, pi.grand_total, pi.restaurant_table, 
            pi.cashier, pi.waiter, u.full_name as waiter_name, pi.net_total, pi.posting_time, 
            pi.total_taxes_and_charges, pi.customer, pi.status, pi.mobile_number, 
            pi.posting_date, pi.rounded_total, pi.order_type 
        FROM `tabPOS Invoice` pi
        LEFT JOIN `tabUser` u ON pi.waiter = u.email
        WHERE pi.branch = %s AND pi.status = 'Draft'
        AND (
            pi.invoice_printed = 1 
            OR (pi.invoice_printed = 0 AND COALESCE(pi.restaurant_table, '') = '')
            OR (pi.invoice_printed = 0 AND pi.order_type = 'Dine In')
        )
        ORDER BY pi.modified desc
        LIMIT %s OFFSET %s
        """,
        (branch, limit, limit_start),
        as_dict=True,
    )
    updatedlist.extend(invoices)

    if len(updatedlist) == limit:
        next = True
        updatedlist.pop()
    else:
        next = False

    return {"data": updatedlist, "next": next}

@frappe.whitelist()
def create_opening_voucher(company: str, pos_profile: str, balance_details: list):
    try:
        
        new_pos_opening = frappe.get_doc(
            {
                "doctype": "POS Opening Entry",
                "period_start_date": frappe.utils.get_datetime(),
                "posting_date": frappe.utils.getdate(),
                "user": frappe.session.user,
                "pos_profile": pos_profile,
                "company": company,
            }
        )
        new_pos_opening.set("balance_details", balance_details)
        new_pos_opening.submit()

        return {"status": "success", "opening_entry": new_pos_opening.name}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "POS Opening Creation Failed")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_closing_preview(pos_opening_entry: str):
    """Return a preview summary for the dialog (doesn't save anything)."""
    opening_entry = frappe.get_doc("POS Opening Entry", pos_opening_entry)
    closing_entry = make_closing_entry_from_opening(opening_entry)

    # waiter summary
    invoices = get_pos_invoices(
        closing_entry.period_start_date,
        closing_entry.period_end_date,
        closing_entry.pos_profile,
        closing_entry.user,
    )
    waiter_map = {}
    for inv in invoices:
        waiter = inv.get("owner") or "Unassigned"
        if waiter not in waiter_map:
            waiter_map[waiter] = {"waiter": waiter, "total": 0.0, "invoices": 0}
        waiter_map[waiter]["invoices"] += 1
        waiter_map[waiter]["total"] += flt(inv.get("grand_total") or 0.0)

    waiter_summary = list(waiter_map.values())
    # Convert child tables on the closing_entry into serializable dicts
    payment_reconciliation = [p.as_dict() for p in closing_entry.payment_reconciliation]
    taxes = [t.as_dict() for t in closing_entry.taxes]
    pos_transactions = [p.as_dict() for p in closing_entry.pos_transactions]

    return {
        "grand_total": closing_entry.grand_total,
        "net_total": closing_entry.net_total,
        "total_quantity": closing_entry.total_quantity,
        "taxes": taxes,
        "payments": payment_reconciliation,
        "pos_transactions": pos_transactions,
        "waiter_summary": waiter_summary,
    }


@frappe.whitelist()
def submit_pos_closing(pos_opening_entry: str, closing_amounts: list = None):
    """Actually create & submit a POS Closing Entry."""
    try:
        opening_entry = frappe.get_doc("POS Opening Entry", pos_opening_entry)
        closing_entry = make_closing_entry_from_opening(opening_entry)

        # inject actual amounts
        if closing_amounts:
            closing_map = {p["mode_of_payment"]: p["closing_amount"] for p in closing_amounts}
            for row in closing_entry.payment_reconciliation:
                row.closing_amount = closing_map.get(row.mode_of_payment, 0)
                row.difference = row.closing_amount - row.expected_amount
        
        closing_entry.insert(ignore_permissions=True)
        closing_entry.submit()
        return {"status": "success", "closing_entry": closing_entry.name}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "POS Closing Failed")
        return {"status": "error", "message": str(e)}
