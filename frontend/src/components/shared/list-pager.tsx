"use client";

import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";

/**
 * Build a compact page window (1 … 4 5 [6] 7 8 … 20) so a long list never
 * renders a hundred page links.
 */
function pageWindow(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "…")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) pages.push("…");
  for (let p = start; p <= end; p++) pages.push(p);
  if (end < total - 1) pages.push("…");
  pages.push(total);
  return pages;
}

/**
 * Page-based list footer. Pages server-side via `onPageChange`; the page size
 * is fixed by the caller and encoded in the query key.
 */
export function ListPager({
  page,
  total,
  pageSize,
  onPageChange,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  const go = (p: number) => (e: React.MouseEvent) => {
    e.preventDefault();
    onPageChange(Math.min(totalPages, Math.max(1, p)));
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-3">
      <p className="text-xs text-muted-foreground">
        Page {page} of {totalPages} · {total.toLocaleString()} total
      </p>
      <Pagination className="mx-0 w-auto justify-end">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              href="#"
              onClick={go(page - 1)}
              className={page === 1 ? "pointer-events-none opacity-50" : ""}
            />
          </PaginationItem>
          {pageWindow(page, totalPages).map((p, i) =>
            p === "…" ? (
              <PaginationItem key={`e-${i}`}>
                <span className="px-2 text-xs text-muted-foreground">…</span>
              </PaginationItem>
            ) : (
              <PaginationItem key={p}>
                <PaginationLink href="#" onClick={go(p)} isActive={p === page}>
                  {p}
                </PaginationLink>
              </PaginationItem>
            )
          )}
          <PaginationItem>
            <PaginationNext
              href="#"
              onClick={go(page + 1)}
              className={page === totalPages ? "pointer-events-none opacity-50" : ""}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}
