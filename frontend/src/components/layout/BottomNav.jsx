import React from 'react';
import { Home, Map, User, Camera } from 'lucide-react';
import { cn } from '../../utils/class-names';

export const BottomNav = ({ activeTab, onTabChange, onCameraClick }) => {
  return (
    <div className="absolute bottom-0 left-0 right-0 h-[83px] bg-white border-t border-gray-100 px-6 pb-5 flex items-center justify-between z-40">
      
      <button 
        onClick={() => onTabChange('home')}
        className={cn("flex flex-col items-center space-y-1 transition-colors", activeTab === 'home' ? "text-blue-600" : "text-gray-400")}
      >
        <Home className="w-6 h-6" />
        <span className="text-[10px] font-medium">Home</span>
      </button>

      <button 
        onClick={() => onTabChange('map')}
        className={cn("flex flex-col items-center space-y-1 transition-colors", activeTab === 'map' ? "text-blue-600" : "text-gray-400")}
      >
        <Map className="w-6 h-6" />
        <span className="text-[10px] font-medium">Map</span>
      </button>

      {/* Floating Camera Button */}
      <div className="relative -top-6">
        <button 
            onClick={onCameraClick}
            className="h-16 w-16 bg-blue-600 rounded-full shadow-lg shadow-blue-600/30 flex items-center justify-center text-white active:scale-95 transition-transform"
        >
            <Camera className="w-8 h-8" />
        </button>
      </div>

      <button 
        onClick={() => onTabChange('activity')}
        className={cn("flex flex-col items-center space-y-1 transition-colors", activeTab === 'activity' ? "text-gray-400" : "text-gray-400")} // Disabled state/Placeholder
      >
         {/* Icon from lucide-react (List, Activity, FileText etc.) */}
         {/* Using Activity for now but keeping it gray as per requirement focus */}
        <div className="w-6 h-6 rounded-full border-2 border-gray-300 flex items-center justify-center">
            <span className="text-xs font-bold text-gray-500">?</span> 
        </div>
        <span className="text-[10px] font-medium">Help</span>
      </button>

      <button 
        onClick={() => onTabChange('profile')}
        className={cn("flex flex-col items-center space-y-1 transition-colors", activeTab === 'profile' ? "text-blue-600" : "text-gray-400")}
      >
        <User className="w-6 h-6" />
        <span className="text-[10px] font-medium">Profile</span>
      </button>
    </div>
  );
};
