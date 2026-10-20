"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useReviewQueue, useReviewIssueMutation, useMe } from "@/queries/index";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { QueryError } from "@/components/shared/query-error";
import { SortHeaders } from "@/components/shared/sort-headers";
import { ListPager } from "@/components/shared/list-pager";
import { useInfiniteScroll } from "@/hooks/use-infinite-scroll";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { ArrowDownToLine, Check, Inbox, MapPin, Rows3, Trash2 } from "lucide-react";
import {
  formatDate,
  humanize,
  severityMeta,
  TYPE_META,
} from "@/lib/format";
import type { Issue } from "@/lib/api";
import { mediaUrl } from "@/lib/api";

const TYPE_OPTIONS = Object.keys(TYPE_META);

function ReviewRow({
  issue,
  onApprove,
  onReject,
  onChangeType,
  processing,
}: {
  issue: Issue;
  onApprove: () => void;
  onReject: () => void;
  onChangeType: (t: string) => void;
  processing: boolean;
}) {
  const sev = severityMeta(issue.severity);

  return (
    <div className="flex items-start gap-4 px-5 py-4 transition-colors hover:bg-muted/40">
      {/* Thumbnail */}
      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg border bg-muted">
        <Image
          src={mediaUrl(issue.image_url)}
          alt=""
          width={64}
          height={64}
          unoptimized
          className="h-full w-full object-cover"
        />
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{humanize(issue.issue_type)}</span>
          <Badge
            variant="outline"
            className="border-orange-200 bg-orange-50 text-orange-700"
          >
            Needs review
          </Badge>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${sev.pill}`}
          >
            {sev.label}
          </span>
        </div>
        {issue.description && (
          <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
            {issue.description}
          </p>
        )}
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            Ward {issue.ward_id}
          </span>
          <span>{formatDate(issue.created_at)}</span>
          <span className="text-muted-foreground/70">
            Confidence {(issue.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-2">
        <Select
          onValueChange={onChangeType}
          disabled={processing}
        >
          <SelectTrigger className="h-8 w-[130px] text-xs">
            <SelectValue placeholder="Change type…" />
          </SelectTrigger>
          <SelectContent>
            {TYPE_OPTIONS.map((t) => (
              <SelectItem key={t} value={t} className="text-xs">
                {TYPE_META[t].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          className="h-8 gap-1 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800"
          onClick={onApprove}
          disabled={processing}
        >
          <Check className="h-3.5 w-3.5" />
          Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-8 gap-1 text-red-600 hover:bg-red-50 hover:text-red-700"
          onClick={onReject}
          disabled={processing}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Reject
        </Button>
      </div>
    </div>
  );
}

export default function ReviewQueuePage() {
  const { data: currentUser } = useMe();
  const router = useRouter();

  // Server-side filter/sort/page state. Confidence ascending by default: the
  // rows the classifier was least sure about are the ones a human should see
  // first, so the queue leads with them rather than with the newest.
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [sevFilter, setSevFilter] = useState<string>("all");
  const [sort, setSort] = useState("confidence");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [loadMode, setLoadMode] = useState<"pages" | "scroll">("pages");
  const PAGE_SIZE = 20;

  const queryParams = useMemo(
    () => ({
      skip: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
      issue_type: typeFilter !== "all" ? typeFilter : undefined,
      severity: sevFilter !== "all" ? Number(sevFilter) : undefined,
      sort,
      order,
    }),
    [page, typeFilter, sevFilter, sort, order]
  );

  const { data, isLoading, isError, error, refetch, isFetching } = useReviewQueue(queryParams);
  const reviewMutation = useReviewIssueMutation();
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [rejectConfirm, setRejectConfirm] = useState<number | null>(null);

  // Accumulated rows for scroll mode, reset whenever the filter/sort identity
  // changes so a new result set starts from scratch.
  const filterKey = `${typeFilter}|${sevFilter}|${sort}|${order}|${loadMode}`;
  const [accumulated, setAccumulated] = useState<Issue[]>([]);
  useEffect(() => {
    setAccumulated([]);
    setPage(1);
  }, [filterKey]);
  useEffect(() => {
    if (loadMode !== "scroll" || !data) return;
    setAccumulated((prev) => {
      const base = page === 1 ? [] : prev;
      const seen = new Set(base.map((i) => i.id));
      return [...base, ...data.items.filter((i) => !seen.has(i.id))];
    });
  }, [data, loadMode, page]);

  const isAdmin = currentUser?.role === "admin" || currentUser?.role === "super_admin";

  useEffect(() => {
    if (currentUser && !isAdmin) {
      router.replace("/dashboard");
    }
  }, [currentUser, isAdmin, router]);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const displayItems = loadMode === "scroll" ? accumulated : items;
  const hasMore = loadMode === "scroll" && displayItems.length < total;
  const sentinelRef = useInfiniteScroll(() => setPage((p) => p + 1), {
    disabled: !hasMore || isFetching,
  });

  if (currentUser && !isAdmin) {
    return null;
  }

  const handleApprove = async (id: number) => {
    setProcessingId(id);
    try {
      await reviewMutation.mutateAsync({ id, action: "approve" });
      toast.success("Issue approved and routed to engineer");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to approve");
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (id: number) => {
    setProcessingId(id);
    setRejectConfirm(null);
    try {
      await reviewMutation.mutateAsync({ id, action: "reject" });
      toast.success("Issue rejected and removed");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to reject");
    } finally {
      setProcessingId(null);
    }
  };

  const handleChangeType = async (id: number, newType: string) => {
    setProcessingId(id);
    try {
      await reviewMutation.mutateAsync({ id, action: "change_type", newType });
      toast.success(`Type changed to ${TYPE_META[newType]?.label ?? newType}`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to change type");
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            {total} {total === 1 ? "issue" : "issues"} waiting for admin review
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      {/* Filters + sort */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={typeFilter} onValueChange={(v) => { setTypeFilter(v); setPage(1); }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {TYPE_OPTIONS.map((t) => (
              <SelectItem key={t} value={t}>
                {TYPE_META[t]?.label ?? t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={sevFilter} onValueChange={(v) => { setSevFilter(v); setPage(1); }}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="All severities" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All severities</SelectItem>
            {[1, 2, 3, 4, 5].map((s) => (
              <SelectItem key={s} value={String(s)}>
                {severityMeta(s).label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <SortHeaders
          className="ml-auto"
          sort={sort}
          order={order}
          onChange={(s, o) => { setSort(s); setOrder(o); setPage(1); }}
          options={[
            { key: "confidence", label: "Confidence" },
            { key: "severity", label: "Severity" },
            { key: "created_at", label: "Newest" },
          ]}
        />

        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => {
            setLoadMode((m) => (m === "pages" ? "scroll" : "pages"));
            setPage(1);
          }}
          title="Toggle between page numbers and load-on-scroll"
        >
          {loadMode === "pages" ? (
            <>
              <ArrowDownToLine className="h-3.5 w-3.5" />
              Load on scroll
            </>
          ) : (
            <>
              <Rows3 className="h-3.5 w-3.5" />
              Page numbers
            </>
          )}
        </Button>
      </div>

      <Card>
        {isError ? (
          <QueryError
            error={error}
            onRetry={() => refetch()}
            title="Could not load the review queue"
            className="border-0 bg-transparent"
          />
        ) : isLoading ? (
          <div className="space-y-1 p-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-4">
                <Skeleton className="h-16 w-16 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
                <Skeleton className="h-8 w-32 rounded" />
              </div>
            ))}
          </div>
        ) : displayItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <Inbox className="h-7 w-7 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-base font-semibold">
              {total === 0 && typeFilter === "all" && sevFilter === "all"
                ? "Queue is empty"
                : "No issues match your filters"}
            </h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {total === 0 && typeFilter === "all" && sevFilter === "all"
                ? "No issues are currently waiting for review. Check back later."
                : "Try adjusting your filters."}
            </p>
          </div>
        ) : (
          <>
            <div className={`divide-y transition-opacity ${isFetching && loadMode === "pages" ? "opacity-60" : ""}`}>
              {displayItems.map((issue) => (
                <ReviewRow
                  key={issue.id}
                  issue={issue}
                  onApprove={() => handleApprove(issue.id)}
                  onReject={() => setRejectConfirm(issue.id)}
                  onChangeType={(t) => handleChangeType(issue.id, t)}
                  processing={processingId === issue.id}
                />
              ))}
            </div>
            {loadMode === "scroll" ? (
              <div className="flex flex-col items-center gap-3 py-6">
                {isFetching && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    Loading more…
                  </div>
                )}
                {hasMore ? (
                  <div ref={sentinelRef} className="h-1 w-full" aria-hidden />
                ) : (
                  <p className="text-xs text-muted-foreground">
                    You&apos;ve reached the end · {total} issues
                  </p>
                )}
              </div>
            ) : (
              <ListPager page={page} total={total} pageSize={PAGE_SIZE} onPageChange={setPage} />
            )}
          </>
        )}
      </Card>

      {/* Reject confirmation */}
      <Dialog
        open={rejectConfirm !== null}
        onOpenChange={(o) => !o && setRejectConfirm(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Reject this issue?</DialogTitle>
            <DialogDescription>
              This will permanently delete the issue record and the uploaded
              photo. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => rejectConfirm !== null && handleReject(rejectConfirm)}
            >
              Yes, reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
