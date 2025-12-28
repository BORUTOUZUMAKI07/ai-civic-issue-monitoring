import React from 'react';

export const MobileShell = ({ children }) => {
  return (
    <div className="flex justify-center items-center min-h-screen bg-gray-200">
      {/* Mobile Device Simulation */}
      <div className="w-full h-full sm:h-[844px] sm:w-[390px] bg-white sm:rounded-[40px] shadow-2xl overflow-hidden relative border-[8px] border-black sm:border-gray-900 ring-2 ring-gray-900/10">
        
        {/* Notch / Status Bar Area */}
        <div className="absolute top-0 left-0 right-0 h-10 bg-white/90 backdrop-blur-md z-50 px-6 flex items-center justify-between text-xs font-semibold text-gray-900">
           <span>9:41</span>
           <div className="flex items-center space-x-2">
              <div className="h-3 w-3 bg-black rounded-full" /> {/* Signal */}
              <div className="h-3 w-3 bg-black rounded-full" /> {/* WiFi */}
              <div className="w-6 h-3 bg-black rounded-[2px]" /> {/* Battery */}
           </div>
        </div>

        {/* Content Area */}
        <div className="h-full pt-10 pb-[83px] overflow-y-auto no-scrollbar scroll-smooth">
          {children}
        </div>

        {/* Home Indicator */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-32 h-1 bg-gray-900 rounded-full z-50 pointer-events-none"></div>
      </div>
    </div>
  );
};
