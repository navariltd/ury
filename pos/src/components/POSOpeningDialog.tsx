import { RefreshCw, AlertTriangle, MonitorX } from 'lucide-react';
import { useState, useEffect } from 'react';
import { Button } from './ui';
import { call } from '../lib/frappe-sdk';
import { getCombinedPosProfile } from '../lib/pos-profile-api';
import CurrencyInput from 'react-currency-input-field';
import { getCurrencySymbol } from '../lib/utils';
import POSClosingDialog from './POSClosingDialog';

interface POSOpeningDialogProps {
  onReload: () => void;
  type: 'opening' | 'closing';
}

const POSOpeningDialog = ({ onReload, type }: POSOpeningDialogProps) => {
  const isOpeningIssue = type === 'opening';
  const [showForm, setShowForm] = useState(false);
  const [showClosingDialog, setShowClosingDialog] = useState(false);
  const [profile, setProfile] = useState<any[]>([]);
  const [balanceDetails, setBalanceDetails] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const handleClosedPOS = () => {
    setShowClosingDialog(false);
    onReload();
  }

  // When form opens, fetch profile and payment methods
  useEffect(() => {
    if (!showForm) return;
    (async () => {
      const p = await getCombinedPosProfile();
      setProfile(p);

      const res = await call.get('frappe.client.get', {
        doctype: 'POS Profile',
        name: p.name,
      });

      setBalanceDetails(
        (res.message?.payments || []).map((pay: any) => ({
          mode_of_payment: pay.mode_of_payment,
          opening_amount: 0,
        }))
      );
    })();
  }, [showForm]);

  const handleSubmit = async () => {
    if (!profile) return;
    setLoading(true);

    try {
      const res = await call.post('ury.ury_pos.api.create_opening_voucher', {
        pos_profile: profile.name,
        company: profile.company,
        branch: profile.branch,
        warehouse: profile.warehouse,
        balance_details: balanceDetails,
      });

      if (res.message?.status === 'success') {
        onReload();
      } else {
        alert(res.message?.message || 'Failed to create POS Opening Entry');
      }
    } finally {
      setLoading(false);
    }
  };
  
  const handleSwitchToDesk = () => {
    // Get the current domain and open /app in a new tab
    const currentDomain = window.location.origin;
    window.open(`${currentDomain}/app`, '_blank');
  };

return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-8 max-w-3xl w-full mx-4 shadow-xl">
        {/* If user needs to close yesterday's POS  */}
        {type === "closing" && showClosingDialog ? (
          <POSClosingDialog onClose={handleClosedPOS} user={null} />
        ) : !showForm ? (
          <div className="text-center">
            {/* Icon */}
            <div
              className={`mx-auto flex items-center justify-center h-16 w-16 rounded-full mb-6 ${
                isOpeningIssue ? 'bg-red-100' : 'bg-orange-100'
              }`}
            >
              {isOpeningIssue ? (
                <RefreshCw className="h-8 w-8 text-red-600" />
              ) : (
                <AlertTriangle className="h-8 w-8 text-orange-600" />
              )}
            </div>

            {/* Title */}
            <h2 className="text-2xl font-bold text-gray-900 mb-4">
              {isOpeningIssue ? 'POS Not Opened' : 'Previous POS Not Closed'}
            </h2>

            <p className="text-gray-600 mb-8 text-lg">
              {isOpeningIssue
                ? 'Please open POS Entry to continue using the system.'
                : 'Please close the previous POS Entry to continue.'}
            </p>

            {/* Buttons */}
            <div className="space-y-3">
              {isOpeningIssue ? (
                <>
                  <Button 
                    onClick={onReload} 
                    className="w-full bg-blue-600 text-white"
                  >
                    <RefreshCw className="w-5 h-5 mr-2" />
                    Reload Page
                  </Button>
                  <Button
                    onClick={() => setShowForm(true)}
                    variant="outline"
                    className="w-full border-gray-300 text-gray-700"
                  >
                    Open POS Entry
                  </Button>
                </>
              ) : (
                <>
                  <Button 
                      onClick={onReload} 
                      className="w-full bg-blue-600 text-white"
                    >
                      <RefreshCw className="w-5 h-5 mr-2" />
                      Reload Page
                  </Button>
                  <Button
                    onClick={() => setShowClosingDialog(true)}
                    className="w-full bg-orange-600 text-white"
                  >
                    <MonitorX className="w-5 h-5 mr-2" />
                    Close Previous POS
                  </Button>
                </>
              )}
            </div>
          </div>
        ) : (
          <div>
            <h2 className="text-xl font-bold mb-4">Create POS Opening Entry</h2>

            {/* Profile details  */}
            <div className="mb-6 space-y-2 text-sm text-gray-700 border rounded p-4 bg-gray-50">
              <div><strong>Company:</strong> {profile.company}</div>
              <div><strong>POS Profile:</strong> {profile.name}</div>
            </div>

            {/* Payment inputs  */}
            {balanceDetails.map((row, idx) => (
              <div key={idx} className="flex justify-between mb-2">
                <span>{row.mode_of_payment}</span>
                <CurrencyInput
                  className="w-28 border rounded px-2 py-1 text-right"
                  placeholder="Opening Amount"
                  decimalsLimit={2}
                  prefix={getCurrencySymbol() + " "}
                  defaultValue={0}
                  onValueChange={(value) => {
                    const updated = [...balanceDetails];
                    updated[idx].opening_amount = parseFloat(value) || 0;
                    setBalanceDetails(updated);
                  }}
                />
              </div>
            ))}

            <div className="flex justify-end gap-2 mt-6">
              <Button onClick={() => setShowForm(false)} variant="outline">
                Cancel
              </Button>
              <Button onClick={handleSubmit} disabled={loading}>
                {loading ? 'Submitting...' : 'Submit'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default POSOpeningDialog; 