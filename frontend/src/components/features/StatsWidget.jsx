import React from 'react';
import { Card } from '../ui/Card';
import { motion } from 'framer-motion';
import { UserCheck, MapPin, Send, Clock } from 'lucide-react';

const StatCard = ({ title, value, subtext, icon: Icon, color, delay }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: delay }}
    >
      <Card className="flex items-center space-x-4 border-slate-100 hover:border-blue-200">
        <div className={`p-3 rounded-xl bg-${color}-50 text-${color}-600`}>
          <Icon className="w-8 h-8" />
        </div>
        <div>
          <p className="text-slate-500 text-xs font-bold uppercase tracking-wider">{title}</p>
          <h3 className="text-2xl font-bold text-slate-900">{value}</h3>
          <p className="text-xs text-slate-400 font-medium">{subtext}</p>
        </div>
      </Card>
    </motion.div>
  );
};

export const StatsWidget = () => {
  const stats = [
    { 
        title: "Staff Active", 
        value: "42", 
        subtext: "Engineers on Field",
        icon: UserCheck, 
        color: "blue", 
        delay: 0.1 
    },
    { 
        title: "Auto-Routed", 
        value: "148", 
        subtext: "Issues Assigned Today",
        icon: Send, 
        color: "green", 
        delay: 0.2 
    },
    { 
        title: "Geofence Hits", 
        value: "12", 
        subtext: "Wards Monitored",
        icon: MapPin, 
        color: "purple", 
        delay: 0.3 
    },
    { 
        title: "Avg Response", 
        value: "18m", 
        subtext: "Faster than SLA",
        icon: Clock, 
        color: "orange", 
        delay: 0.4 
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      {stats.map((stat, index) => (
        <StatCard key={stat.title} {...stat} />
      ))}
    </div>
  );
};
