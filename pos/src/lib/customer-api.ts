import { DOCTYPES } from '../data/doctypes';
import { db, call } from './frappe-sdk';

export interface Customer {
  name: string;
  owner: string;
  creation: string;
  modified: string;
  modified_by: string;
  docstatus: number;
  idx: number;
  naming_series: string;
  customer_name: string;
  customer_type: string;
  mobile_number: string;
  customer_group: string;
  territory: string;
  is_internal_customer: number;
  language: string;
  default_commission_rate: number;
  so_required: number;
  dn_required: number;
  is_frozen: number;
  disabled: number;
  doctype: string;
  companies: any[];
  credit_limits: any[];
  accounts: any[];
  sales_team: any[];
  portal_users: any[];
}

export interface CreateCustomerData {
  customer_name: string;
  mobile_number: string;
  customer_group?: string;
  territory?: string;
}

export interface CreateCustomerResponse {
  data: Customer;
  _server_messages?: string;
}

export async function getCustomerGroups() {
  const groups = await db.getDocList(DOCTYPES.CUSTOMER_GROUP, {
    fields: ['name'],
    limit: "*" as unknown as number,
    orderBy: {
      field: 'name',
      order: 'asc',
    },
  });
  return groups;
}

export async function getCustomerTerritories() {
  const territories = await db.getDocList(DOCTYPES.CUSTOMER_TERRITORY, {
    fields: ['name'],
    limit: "*" as unknown as number,
    orderBy: {
      field: 'name',
      order: 'asc',
    },
  });
  return territories;
}

export async function addCustomer(customerData: CreateCustomerData): Promise<CreateCustomerResponse> {
  try {
    const response = await db.createDoc(DOCTYPES.CUSTOMER, customerData);
    return { data: response as Customer };
  } catch (error) {
    console.error('Error creating customer:', error);
    throw error;
  }
}

export async function searchCustomers(search: string, limit = 5) {
  if (!search.trim()) return [];
  try {
    const res = await call.get('frappe.utils.global_search.search', {
      text: search,
      doctype: DOCTYPES.CUSTOMER,
      limit,
    });
    return res.message || [];
  } catch (error) {
    console.error('Customer search error:', error);
    throw error;
  }
}

export async function getCustomerByName(customerName: string): Promise<Customer | null> {
  try {
    if (!customerName) return null;
    const customer = await db.getDoc(DOCTYPES.CUSTOMER, customerName);
    return customer as Customer;
  } catch (error) {
    console.error(`Error fetching customer ${customerName}:`, error);
    return null;
  }
}

export async function getDefaultCustomerFromProfile(profile: any): Promise<Customer | null> {
  try {
    if (!profile?.customer) return null;

    // Fetch full customer document
    const customer = await getCustomerByName(profile.customer);
    return customer;
  } catch (error) {
    console.error("Error fetching default customer:", error);
    return null;
  }
}
