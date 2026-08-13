"use client";

import dynamic from "next/dynamic";
import { useHeatmapData } from "@/queries/index";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MapPin } from "lucide-react";
import { humanize, TYPE_META } from "@/lib/format";

const IssueMap = dynamic(
  () => import("@/components/maps/IssueMap").then((m) => m.IssueMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[600px] items-center justify-center bg-muted">
        <p className="text-sm text-muted-foreground">Loading map…</p>
      </div>
    ),
  }
);

export default function MapPage() {
  const { data: points, isLoading } = useHeatmapData();

  const pointCount = points?.length || 0;
  const categoryCount = Object.keys(TYPE_META).filter(
    (t) => points?.some((p) => p.type === t)
  ).length;

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden">
        <div className="relative">
          {isLoading ? (
            <Skeleton className="h-[600px] w-full rounded-none" />
          ) : points && pointCount > 0 ? (
            <IssueMap points={points} />
          ) : (
            <div className="flex h-[600px] flex-col items-center justify-center bg-muted">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-background">
                <MapPin className="h-7 w-7 text-muted-foreground" />
              </div>
              <p className="mt-4 text-sm font-medium">No issues to display</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Reported issues will appear on the map as they come in.
              </p>
            </div>
          )}

          {pointCount > 0 && (
            <div className="pointer-events-none absolute inset-0">
              <div className="absolute right-4 top-4 flex items-center gap-2 rounded-full border bg-card/95 px-3.5 py-1.5 text-xs font-medium shadow-sm backdrop-blur">
                <span className="h-2 w-2 rounded-full bg-blue-500" />
                {pointCount} issues · {categoryCount} categories
              </div>

              <div className="absolute bottom-4 left-4 max-w-[calc(100%-2rem)] rounded-xl border bg-card/95 p-3.5 shadow-lg backdrop-blur">
                <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Legend
                </p>
                <div className="grid grid-cols-2 gap-x-5 gap-y-2 sm:grid-cols-4 lg:grid-cols-7">
                  {Object.entries(TYPE_META).map(([key, meta]) => (
                    <div key={key} className="flex items-center gap-2 text-xs">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: meta.color }}
                      />
                      <span className="text-muted-foreground">{meta.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
        <p className="inline-flex items-center gap-1.5">
          <MapPin className="h-4 w-4" />
          Vadodara, Gujarat · coordinates shown per report
        </p>
        {pointCount > 0 && (
          <p>
            Most reported:{" "}
            <span className="font-medium text-foreground">
              {humanize(
                Object.entries(
                  (points ?? []).reduce<Record<string, number>>((acc, p) => {
                    acc[p.type] = (acc[p.type] ?? 0) + 1;
                    return acc;
                  }, {})
                ).sort((a, b) => b[1] - a[1])[0]?.[0] ?? ""
              )}
            </span>
          </p>
        )}
      </div>
    </div>
  );
}
