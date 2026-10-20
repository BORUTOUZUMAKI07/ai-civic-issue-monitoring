"use client";

import { usePublicStats } from "@/queries/index";
import { ScrollReveal } from "@/components/ScrollReveal";
import { CheckCircle2, HardHat, MapPinned, TrendingUp } from "lucide-react";

/**
 * Real, aggregate platform counters for the landing page.
 *
 * Sourced from ``GET /dashboard/public-stats`` (unauthenticated, counts only).
 * The block is hidden entirely while loading and on any failure, and hides
 * itself when the platform has no data yet -- so the marketing page never
 * shows an invented number or a row of zeroes dressed up as traction.
 */
export function LiveStats() {
  const { data, isLoading, isError } = usePublicStats();

  if (isLoading || isError || !data || data.total_issues === 0) {
    return null;
  }

  const resolutionRate =
    data.total_issues > 0
      ? Math.round((data.resolved_issues / data.total_issues) * 100)
      : 0;

  const stats = [
    {
      icon: TrendingUp,
      value: data.total_issues.toLocaleString(),
      label: "Issues reported",
    },
    {
      icon: CheckCircle2,
      value: `${resolutionRate}%`,
      label: "Resolved",
    },
    {
      icon: MapPinned,
      value: data.wards_covered.toLocaleString(),
      label: "Wards covered",
    },
    {
      icon: HardHat,
      value: data.active_engineers.toLocaleString(),
      label: "Engineers available",
    },
  ];

  return (
    <section className="border-y border-border/60 bg-card/50">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-6 px-6 py-12 md:grid-cols-4">
        {stats.map((s, i) => (
          <ScrollReveal key={s.label} delay={i * 0.06} className="text-center">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-sm">
              <s.icon className="h-5 w-5" />
            </div>
            <p className="text-3xl font-semibold tracking-tight">{s.value}</p>
            <p className="mt-1 text-sm text-muted-foreground">{s.label}</p>
          </ScrollReveal>
        ))}
      </div>
    </section>
  );
}
