"use client";

import { useState } from "react";
import { useReviewQueue, useReviewIssueMutation } from "@/queries/index";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { Check, Eye, Inbox, MapPin, Trash2 } from "lucide-react";
import {
  formatDate,
  humanize,
  severityMeta,
  TYPE_META,
} from "@/lib/format";
import type { Issue } from "@/lib/api";

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
        <img
          src={issue.image_url}
          alt=""
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
  const { data, isLoading, refetch } = useReviewQueue({ limit: 50 });
  const reviewMutation = useReviewIssueMutation();
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [rejectConfirm, setRejectConfirm] = useState<number | null>(null);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

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
            {total} issues waiting for admin review
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      <Card>
        {isLoading ? (
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
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <Inbox className="h-7 w-7 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-base font-semibold">Queue is empty</h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              No issues are currently waiting for review. Check back later.
            </p>
          </div>
        ) : (
          <div className="divide-y">
            {items.map((issue) => (
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
