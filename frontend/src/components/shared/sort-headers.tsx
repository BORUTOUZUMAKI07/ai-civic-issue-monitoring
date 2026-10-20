"use client";

import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SortOption {
  key: string;
  label: string;
}

/**
 * A row of clickable, sortable column headers.
 *
 * `sort`/`order` are lifted state owned by the page; clicking a header either
 * flips the direction (same column) or selects the new column ascending. The
 * chevron reflects which column is active and which way it sorts.
 */
export function SortHeaders({
  options,
  sort,
  order,
  onChange,
  className,
}: {
  options: SortOption[];
  sort: string;
  order: "asc" | "desc";
  onChange: (sort: string, order: "asc" | "desc") => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {options.map((o) => {
        const active = sort === o.key;
        const Icon = !active ? ChevronsUpDown : order === "asc" ? ArrowUp : ArrowDown;
        return (
          <button
            key={o.key}
            type="button"
            onClick={() => onChange(o.key, active && order === "desc" ? "asc" : "desc")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              active
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            {o.label}
            <Icon className="h-3.5 w-3.5" />
          </button>
        );
      })}
    </div>
  );
}
