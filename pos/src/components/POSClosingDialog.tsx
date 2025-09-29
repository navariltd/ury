import React, { useEffect, useState } from "react";
import CurrencyInput from "react-currency-input-field";
import { X, FileText, Loader2, Users } from "lucide-react";
import { Dialog, DialogContent, Button } from "./ui";
import { call } from "../lib/frappe-sdk";
import { checkPOSOpening } from "../lib/pos-opening-api";
import { formatCurrency, getCurrencySymbol } from "../lib/utils";

interface POSClosingDialogProps {
  onClose: () => void;
  user: any;
}

const POSClosingDialog: React.FC<POSClosingDialogProps> = ({ onClose, user }) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [openingEntry, setOpeningEntry] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<any | null>(null);
  const currencySymbol = getCurrencySymbol();

  useEffect(() => {
    const fetchData = async () => {
      try {
        // find open POS Opening Entry
        const opening = await checkPOSOpening();
        if (!opening?.message) {
          setError("No active POS opening entry found.");
          return;
        }
        setOpeningEntry(opening.message.opening_entry);

        // Preview the summary
        const res = await call.get("ury.ury_pos.api.get_closing_preview", {
          pos_opening_entry: opening.message.opening_entry,
        });

        if (res.message) {
          setSummary(res.message);
        }
      } catch (err) {
        console.error("Error loading POS data", err);
        setError("Failed to fetch POS closing data.");
      }
    };

    fetchData();
  }, [user]);

  const handleClosePOS = async () => {
    setIsProcessing(true);
    setError(null);
    try {
      const res = await call.post("ury.ury_pos.api.submit_pos_closing", {
        pos_opening_entry: openingEntry,
        closing_amounts: summary.payments.map((p: any) => ({
          mode_of_payment: p.mode_of_payment,
          closing_amount: p.closing_amount || 0,
        }))
      });

      if (res.message?.status === "success") {
        if ((window as any).showToast) {
          (window as any).showToast.success("POS closed successfully");
        }
        window.location.reload();
        onClose();
      } else {
        setError(res.message?.message || "Failed to close POS.");
      }
    } catch (err: any) {
      console.error("Error closing POS:", err);
      setError("Failed to close POS.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <Dialog open={true} onOpenChange={() => {}} dismissible={false}>
      <DialogContent
        variant="xlarge"
        className="bg-white w-full max-w-4xl max-h-[90vh] flex flex-col p-0"
        showCloseButton={false}
      >
        <div className="flex justify-between items-center p-4 border-b border-gray-200">
          <h2 className="text-2xl font-bold">Close POS</h2>
          <Button onClick={onClose} variant="ghost" size="icon">
            <X className="w-5 h-5" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="mb-6 p-4 bg-red-50 border-l-4 border-red-400 rounded-r-lg text-sm text-red-700">
              {error}
            </div>
          )}

            {/* Invoices */}
            {summary?.pos_transactions?.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                  <FileText className="w-5 h-5" /> Invoices
                </h3>
                <ul className="divide-y border rounded-md">
                  {summary.pos_transactions.map((inv: any) => (
                    <li key={inv.name} className="flex justify-between px-4 py-2 text-sm">
                      <span className="w-32">{inv.pos_invoice}</span>
                      <span className="w-28">{inv.posting_date}</span>
                      <span className="w-36">{formatCurrency(inv.grand_total || 0)}</span>
                    </li>
                  ))}
                </ul>
                <div className="flex justify-between mt-4 font-semibold">
                  <span>Total</span>
                  <span>{formatCurrency(summary.grand_total)}</span>
                </div>
              </div>
            )}

          {/* Summary by Waiter */}
          {summary?.waiter_summary?.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <Users className="w-5 h-5" /> Summary by Waiter
              </h3>
              <ul className="divide-y border rounded-md">
                {summary.waiter_summary.map((row: any) => (
                  <li key={row.waiter} className="flex justify-between px-4 py-2 text-sm">
                    <span>
                      {row.waiter} ({row.invoices} invoices)
                    </span>
                    <span>{formatCurrency(row.total)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Payments */}
          {summary?.payments?.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold mb-3">Payments</h3>
              <ul className="divide-y border rounded-md">
                {summary.payments.map((row: any, idx: number) => (
                  <li key={idx} className="flex items-center justify-between px-4 py-2 text-sm gap-2">
                    <span className="w-48 truncate">{row.mode_of_payment}</span>
                    <CurrencyInput
                      className="w-36 border rounded px-2 py-1 text-right"
                      placeholder="Enter actual"
                      decimalsLimit={2}
                      prefix={currencySymbol + " "}
                      defaultValue={row.expected_amount}
                      onValueChange={(value) => {
                        const numeric = value ? parseFloat(value) : 0;
                        setSummary((prev: any) => {
                          const updated = { ...prev };
                          updated.payments[idx].closing_amount = numeric;
                          return updated;
                        });
                      }}
                    />
                    <span className="w-32 text-right">{formatCurrency(row.expected_amount)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Taxes */}
          {summary?.taxes?.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold mb-3">Taxes</h3>
              <ul className="divide-y border rounded-md">
                {summary.taxes.map((row: any, idx: number) => (
                  <li key={idx} className="flex justify-between px-4 py-2 text-sm">
                    <span>
                      {row.account_head} ({row.rate}%)
                    </span>
                    <span>{formatCurrency(row.amount)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-200">
          <Button
            onClick={handleClosePOS}
            disabled={isProcessing || !openingEntry}
            className="w-full"
          >
            {isProcessing ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Closing...
              </span>
            ) : (
              "Confirm Close"
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default POSClosingDialog;
