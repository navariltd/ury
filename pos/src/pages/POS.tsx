import React, { useState, useRef } from "react";
import { Star, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import OrderPanel from "../components/OrderPanel";
import ProductDialog from "../components/ProductDialog";
import MenuList from "../components/MenuList";
import { usePOSStore } from "../store/pos-store";
import { cn } from "../lib/utils";
import { Spinner } from "../components/ui/spinner";
import InitialLoader from "../components/InitialLoader";

export default function POS() {
  const {
    quickFilter,
    setQuickFilter,
    setSelectedItem,
    addToOrder,
    loading,
    error,
    isMenuInteractionDisabled,
    isInitializing,
  } = usePOSStore();

  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const clickTimerRef = useRef<NodeJS.Timeout | null>(null);
  const clickCountRef = useRef(0);

  const handleItemClick = (item: any) => {
    if (isMenuInteractionDisabled()) return;

    clickCountRef.current += 1;

    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current);
    }

    clickTimerRef.current = setTimeout(() => {
      if (clickCountRef.current === 1) {
        // Single click - add to cart
        addToOrder({ ...item, quantity: 1 });
      } else if (clickCountRef.current === 2) {
        // Double click - open dialog
        setSelectedItem(item);
        setIsDialogOpen(true);
      }
      clickCountRef.current = 0;
    }, 250); // 250ms threshold for double click
  };

  const QuickFilterButton = ({
    filter,
    icon: Icon,
    label,
  }: {
    filter: "all" | "special";
    icon: React.ElementType;
    label: string;
  }) => (
    <button
      onClick={() => setQuickFilter(filter)}
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-colors",
        quickFilter === filter
          ? "bg-blue-100 text-blue-700"
          : "bg-gray-100 text-gray-700 hover:bg-gray-200",
        isMenuInteractionDisabled() &&
          "opacity-50 cursor-not-allowed pointer-events-none",
      )}
      disabled={isMenuInteractionDisabled()}
    >
      <Icon className='w-4 h-4' />
      {label}
    </button>
  );

  if (isInitializing) {
    return <InitialLoader />;
  }

  if (error) {
    return (
      <div className='flex items-center justify-center h-screen'>
        <div className='text-center'>
          <p className='text-xl font-semibold text-red-600 mb-2'>
            Failed to load POS
          </p>
          <p className='text-gray-600'>{error}</p>
          <button
            onClick={() => window.location.reload()}
            className='mt-4 px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700'
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className='flex-1 flex items-center justify-center'>
        <Spinner message='Loading menu items...' />
      </div>
    );
  }

  if (error) {
    return (
      <div className='flex-1 flex items-center justify-center'>
        <div className='text-center'>
          <p className='text-lg font-medium text-red-600'>Error loading menu</p>
          <p className='text-sm text-gray-500 mt-2'>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className='flex flex-1 overflow-hidden'>
      {/* Desktop Sidebar */}
      <div className='hidden lg:block'>
        <Sidebar disabled={isMenuInteractionDisabled()} />
      </div>

      {/* Mobile Sidebar Overlay */}
      {mobileSidebarOpen && (
        <>
          <div
            className='lg:hidden fixed inset-0 bg-black bg-opacity-50 z-40'
            onClick={() => setMobileSidebarOpen(false)}
          />
          <div className='lg:hidden fixed inset-y-0 left-0 w-64 bg-white z-50 shadow-xl'>
            <Sidebar disabled={isMenuInteractionDisabled()} />
          </div>
        </>
      )}

      <div className='flex-1 flex flex-col h-screen overflow-hidden lg:pr-96'>
        <div className='p-4 bg-white border-b border-gray-200'>
          <div className='max-w-screen-xl mx-auto space-y-3'>
            {/* Mobile Category Button */}
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className='lg:hidden w-full px-4 py-2.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-left font-medium text-gray-700 transition-colors'
            >
              Categories
            </button>

            <div className='flex items-center justify-between gap-2'>
              <div className='flex items-center gap-2 overflow-x-auto overflow-y-hidden'>
                {/* <SearchBar
                  value={searchQuery}
                  onChange={setSearchQuery}
                  onVisibilityChange={setShowSearch}
                  isVisible={showSearch}
                  disabled={isMenuInteractionDisabled()}
                /> */}

                <QuickFilterButton filter='all' icon={Star} label='All' />
                <QuickFilterButton
                  filter='special'
                  icon={TrendingUp}
                  label='Special Items'
                />
              </div>

              {/* Link to Orders Page */}
              <Link
                to='/orders'
                className='flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors whitespace-nowrap'
              >
                <svg
                  className='w-4 h-4'
                  fill='none'
                  stroke='currentColor'
                  viewBox='0 0 24 24'
                >
                  <path
                    strokeLinecap='round'
                    strokeLinejoin='round'
                    strokeWidth={2}
                    d='M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
                  />
                </svg>
                <span className='hidden sm:inline'>Orders</span>
              </Link>
            </div>
          </div>
        </div>

        <MenuList onItemClick={handleItemClick} />
      </div>
      <OrderPanel />
      {isDialogOpen && <ProductDialog onClose={() => setIsDialogOpen(false)} />}
    </div>
  );
}
