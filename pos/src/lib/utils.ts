import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { storage } from './storage';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getCurrencySymbol(): string {
  return storage.getItem("currencySymbol") || "";
}

export function formatCurrency(amount: number, currencyCode?: string): string {
  const symbol = getCurrencySymbol();
  const code = currencyCode || storage.getItem("currencyCode") || "USD";

  const formatter = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: code,
    currencyDisplay: "symbol",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })

  let formatted = formatter.format(amount);
  if (symbol) {
    formatted = formatted.replace(/^[^\d]+/, symbol + " ")
  }
  return formatted;
}
