import { FileText } from "lucide-react";
import { cn } from "../lib/utils";
import { Button } from "./ui";
import { getOrderStatusTypes, OrderStatusType } from "../data/order-types";
import { usePOSStore } from "../store/pos-store";

interface OrderStatusSidebarProps {
  disabled?: boolean;
  selectedStatus: OrderStatusType;
  setSelectedStatus: (status: OrderStatusType) => void;
  getStatusCount?: (status: OrderStatusType) => number;
}

const OrderStatusSidebar = ({
  disabled,
  selectedStatus,
  setSelectedStatus,
}: OrderStatusSidebarProps) => {
  const { posProfile } = usePOSStore();

  // Get the appropriate status types based on POS profile settings
  const statusTypes = getOrderStatusTypes(
    posProfile?.view_all_status,
    posProfile?.paid_limit,
  );

  return (
    <div
      className={cn(
        // Desktop: fixed sidebar
        "lg:w-64 bg-white border-r lg:border-r border-b lg:border-b-0 border-gray-200 lg:h-full flex flex-col",
        // Mobile: horizontal scroll
        "w-full",
        disabled && "opacity-50 pointer-events-none",
      )}
    >
      <nav className='flex lg:flex-col overflow-x-auto lg:overflow-x-visible flex-1 p-2 lg:p-6 hide-scrollbar'>
        <div className='flex lg:flex-col gap-2 lg:gap-0 lg:bg-gray-50 lg:border lg:border-gray-200 rounded-lg lg:p-4 min-w-full'>
          {/* Section Title - Hidden on mobile */}
          <h2 className='hidden lg:block text-xs font-medium text-gray-500 uppercase tracking-wide mb-3 px-1'>
            Order Status
          </h2>

          {/* Status Items */}
          <div className='flex lg:flex-col lg:space-y-1 gap-2 lg:gap-0 whitespace-nowrap lg:whitespace-normal'>
            {statusTypes.map((status) => (
              <Button
                key={status.value}
                onClick={() =>
                  setSelectedStatus(status.value as OrderStatusType)
                }
                variant='ghost'
                className={cn(
                  "lg:w-full flex items-center justify-between px-3 py-2.5 text-sm font-medium transition-all duration-200 group relative",
                  selectedStatus === status.value
                    ? "bg-white text-gray-900 shadow-sm font-semibold"
                    : "text-gray-700 hover:bg-white/60 hover:text-gray-900",
                )}
                disabled={disabled}
              >
                {/* Active indicator bar - Desktop only */}
                {selectedStatus === status.value && (
                  <div className='hidden lg:block absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-blue-600 rounded-r-full' />
                )}
                <div className='flex items-center gap-3 ml-0 lg:ml-1'>
                  <FileText className='w-4 h-4 text-gray-500' />
                  <span>{status.label}</span>
                </div>
              </Button>
            ))}
          </div>
        </div>
      </nav>
    </div>
  );
};

export default OrderStatusSidebar;
