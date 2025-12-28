import React from 'react';
import { MapPin, Clock } from 'lucide-react';
import { Card } from '../ui/Card';

const IssueFeedItem = ({ title, status, location, time, image }) => (
  <div className="bg-white p-4 rounded-2xl shadow-sm border border-gray-100 flex gap-4 mb-3 active:scale-[0.98] transition-transform">
    <div className="h-20 w-20 rounded-xl bg-gray-100 shrink-0 overflow-hidden">
        {image ? (
            <img src={image} alt={title} className="h-full w-full object-cover" />
        ) : (
            <div className="h-full w-full bg-gray-200 animate-pulse" />
        )}
    </div>
    <div className="flex-1 min-w-0">
        <div className="flex justify-between items-start">
            <h3 className="font-bold text-gray-900 truncate">{title}</h3>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide
                ${status === 'Resolved' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                {status}
            </span>
        </div>
        <div className="mt-2 space-y-1">
            <div className="flex items-center text-xs text-gray-500">
                <MapPin className="w-3 h-3 mr-1" />
                {location}
            </div>
            <div className="flex items-center text-xs text-gray-400">
                <Clock className="w-3 h-3 mr-1" />
                {time}
            </div>
        </div>
    </div>
  </div>
);

export const HomeScreen = () => {
  return (
    <div className="p-6">
      <header className="mb-6">
        <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">CityPulse</h1>
        <p className="text-gray-500 font-medium">Vadodara Municipal Corp.</p>
      </header>

      {/* Stats Row */}
      <div className="flex gap-3 mb-8 overflow-x-auto no-scrollbar pb-2">
        <div className="flex-1 min-w-[140px] bg-blue-600 text-white p-4 rounded-2xl shadow-lg shadow-blue-600/20">
            <p className="text-blue-100 text-xs font-bold uppercase">My Reports</p>
            <p className="text-3xl font-bold mt-1">12</p>
        </div>
        <div className="flex-1 min-w-[140px] bg-white p-4 rounded-2xl shadow-sm border border-gray-100">
            <p className="text-gray-400 text-xs font-bold uppercase">Resolved</p>
            <p className="text-3xl font-bold mt-1 text-green-600">8</p>
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900">Recent Activity</h2>
        <button className="text-blue-600 text-sm font-semibold">See All</button>
      </div>

      <div>
        <IssueFeedItem 
            title="Pothole on Crossroad"
            status="Pending"
            location="Ward-4, Makarpura"
            time="2 hours ago"
            image="https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?auto=format&fit=crop&q=80&w=200"
        />
        <IssueFeedItem 
            title="Garbage Dump"
            status="Resolved"
            location="Ward-7, Fatehgunj"
            time="Yesterday"
            image="https://images.unsplash.com/photo-1530587191326-6f4be55e00b3?auto=format&fit=crop&q=80&w=200"
        />
        <IssueFeedItem 
            title="Broken Streetlight"
            status="Pending"
            location="Ward-2, Harni"
            time="2 days ago"
            image="https://images.unsplash.com/photo-1565514020128-2c26e633d6b0?auto=format&fit=crop&q=80&w=200"
        />
      </div>
    </div>
  );
};
