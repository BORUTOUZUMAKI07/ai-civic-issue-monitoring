"use client";

import dynamic from "next/dynamic";
import { useHeatmapData } from "@/queries/index";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const IssueMap = dynamic(() => import("@/components/maps/IssueMap").then((m) => m.IssueMap), {
  ssr: false,
  loading: () => (
    <div className="h-[600px] bg-muted rounded-lg flex items-center justify-center">
      <p className="text-muted-foreground">Loading map...</p>
    </div>
  ),
});

const LEGEND_ITEMS = [
  { category: "pothole", label: "Pothole", color: "#ef4444" },
  { category: "garbage", label: "Garbage", color: "#f59e0b" },
  { category: "broken_streetlight", label: "Street Light", color: "#3b82f6" },
  { category: "waterlogging", label: "Waterlogging", color: "#06b6d4" },
  { category: "road_damage", label: "Road Damage", color: "#f97316" },
  { category: "debris", label: "Debris", color: "#8b5cf6" },
  { category: "sewage", label: "Sewage", color: "#14b8a6" },
];

export default function MapPage() {
  const { data: points, isLoading } = useHeatmapData();

  const pointCount = points?.length || 0;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Issue Map</h1>
          <p className="text-sm text-muted-foreground mt-1">Vadodara Municipal Corporation — {pointCount} issues mapped</p>
        </div>
        <Badge variant="outline">{pointCount} points</Badge>
      </div>

      <Card className="overflow-hidden">
        <CardContent className="p-0">
          <div className="h-[550px] rounded-lg overflow-hidden">
            {isLoading ? (
              <div className="h-full bg-muted flex items-center justify-center">
                <p className="text-muted-foreground">Loading map...</p>
              </div>
            ) : points && pointCount > 0 ? (
              <IssueMap points={points} />
            ) : (
              <div className="h-full bg-muted flex items-center justify-center">
                <p className="text-muted-foreground">No issues to display</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-3">
        {LEGEND_ITEMS.map(({ category, label, color }) => (
          <div key={category} className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border/50 bg-background">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-sm">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
