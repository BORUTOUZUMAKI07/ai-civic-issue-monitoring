import React, { useState } from 'react';
import { Activity, Camera, Bell, LayoutDashboard, ClipboardCheck } from 'lucide-react';
import { StatsWidget } from './components/features/StatsWidget';
import { MapView } from './components/features/MapView';
import { IssueReportModal } from './components/features/IssueReportModal';
import { ResolutionModal } from './components/features/ResolutionModal';
import { Button } from './components/ui/Button';
import { Toaster } from 'sonner';

function App() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isResolutionModalOpen, setIsResolutionModalOpen] = useState(false);
  const [viewMode, setViewMode] = useState('standard'); // 'standard' | 'map-focus'

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
        <Toaster position="top-center" theme="light" />
        
        {/* Navbar */}
        <nav className="border-b border-slate-200 bg-white sticky top-0 z-50 shadow-sm">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="bg-blue-600 p-2 rounded-lg">
                        <Activity className="w-5 h-5 text-white" />
                    </div>
                    <span className="text-xl font-bold text-slate-800 tracking-tight">
                        CityPulse
                    </span>
                    <span className="hidden md:inline-block px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-500">
                        ADMIN PORTAL
                    </span>
                </div>
                <div className="flex items-center gap-4">
                    <button className="p-2 text-slate-500 hover:text-slate-700 transition-colors relative">
                        <Bell className="w-5 h-5" />
                        <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
                    </button>
                    <div className="h-9 w-9 rounded-full bg-slate-200 border border-slate-300 overflow-hidden flex items-center justify-center">
                        <span className="font-bold text-slate-500 text-sm">JD</span>
                    </div>
                </div>
            </div>
        </nav>

        {/* Main Content */}
        <main className={viewMode === 'standard' ? "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8" : "h-[calc(100vh-64px)] w-full relative"}>
            
            {/* Header Section (Conditionally rendered or floating in map mode) */}
            {viewMode === 'standard' && (
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-extrabold text-slate-900">Ward Overview</h1>
                    <p className="text-slate-500 mt-1">Vadodara Municipal Corporation • Real-time Monitoring</p>
                </div>
                <div className="flex gap-3">
                     <Button variant="secondary" className="shadow-sm" onClick={() => setViewMode('map-focus')}>
                        <LayoutDashboard className="w-4 h-4 mr-2" />
                        Focus Map
                     </Button>
                     <Button variant="secondary" className="shadow-sm bg-green-50 border-green-200 text-green-700 hover:bg-green-100" onClick={() => setIsResolutionModalOpen(true)}>
                        <ClipboardCheck className="w-4 h-4 mr-2" />
                        Resolve Issue
                     </Button>
                    <Button onClick={() => setIsModalOpen(true)}>
                        <Camera className="w-5 h-5 mr-2" />
                        New Report
                    </Button>
                </div>
            </div>
            )}

            {/* Stats Row */}
            {viewMode === 'standard' && <StatsWidget />}

            {/* Map Section */}
            <div className={viewMode === 'standard' ? "grid grid-cols-1 lg:grid-cols-3 gap-6" : "h-full w-full"}>
                <div className={viewMode === 'standard' ? "lg:col-span-3 h-[600px]" : "h-full w-full"}>
                    <div className={viewMode === 'standard' ? "bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-1 h-full" : "h-full w-full"}>
                        <MapView />
                        
                        {/* Floating Controls for Map Mode */}
                        {viewMode === 'map-focus' && (
                            <div className="absolute top-4 left-4 z-[1000] flex gap-2">
                                <Button variant="secondary" className="shadow-lg bg-white" onClick={() => setViewMode('standard')}>
                                    <LayoutDashboard className="w-4 h-4 mr-2" />
                                    Back to Dashboard
                                </Button>
                                <Button className="shadow-lg" onClick={() => setIsModalOpen(true)}>
                                    <Camera className="w-5 h-5 mr-2" />
                                    Report
                                </Button>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </main>

        {/* Modals */}
        <IssueReportModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
        <ResolutionModal isOpen={isResolutionModalOpen} onClose={() => setIsResolutionModalOpen(false)} />
    </div>
  );
}

export default App;
