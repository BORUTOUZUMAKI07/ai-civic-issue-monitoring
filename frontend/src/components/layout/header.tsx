"use client";

import { Bell, User } from "lucide-react";

export function Header() {
  return (
    <header className="flex items-center justify-between px-6 py-4 border-b">
      <h1 className="text-lg font-semibold">CivicPulse</h1>
      <div className="flex items-center gap-4">
        <button className="p-2 rounded-lg hover:bg-muted">
          <Bell className="h-5 w-5" />
        </button>
        <button className="p-2 rounded-lg hover:bg-muted">
          <User className="h-5 w-5" />
        </button>
      </div>
    </header>
  );
}
