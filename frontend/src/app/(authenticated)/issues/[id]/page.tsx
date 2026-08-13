"use client";

import { use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useIssue } from "@/queries/index";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { IssueTypeIcon } from "@/components/shared/issue-icon";
import {
  ArrowLeft,
  Crosshair,
  MapPin,
  Radio,
  RefreshCw,
  ShieldAlert,
  User,
} from "lucide-react";
import {
  formatDate,
  humanize,
  severityMeta,
  STATUS_META,
} from "@/lib/format";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SimilarResponse {
  issue_id: number;
  similar_issues: Array<{
    issue_id: number;
    description: string;
    similarity: number;
    issue_type: string;
  }>;
  rag_context: string;
  count: number;
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-medium ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

export default function IssueDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const issueId = parseInt(id, 10);
  const { data: issue, isLoading } = useIssue(issueId);
  const router = useRouter();

  const similarQuery = useQuery<SimilarResponse>({
    queryKey: ["similar-issues", issueId],
    queryFn: () => apiFetch(`/api/v1/issues/similar/${issueId}`),
    enabled: !!issueId,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Skeleton className="h-9 w-9 rounded-lg" />
          <Skeleton className="h-7 w-48" />
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Skeleton className="h-64 rounded-xl" />
            <Skeleton className="h-40 rounded-xl" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-48 rounded-xl" />
            <Skeleton className="h-56 rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!issue) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
          <ShieldAlert className="h-7 w-7 text-muted-foreground" />
        </div>
        <h2 className="mt-4 text-base font-semibold">Issue not found</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          This report may have been removed or the link is incorrect.
        </p>
        <Button asChild variant="outline" className="mt-5">
          <Link href="/issues">Back to issues</Link>
        </Button>
      </div>
    );
  }

  const sev = severityMeta(issue.severity);
  const status = STATUS_META[issue.status] ?? {
    label: humanize(issue.status),
    pill: "bg-muted text-muted-foreground ring-muted",
  };
  const imageUrl = issue.image_url?.startsWith("http")
    ? issue.image_url
    : `${API_BASE}${issue.image_url ?? ""}`;

  const similarIssues = similarQuery.data?.similar_issues ?? [];

  const nextAction =
    issue.status === "reported"
      ? { label: "Assign to engineer", next: "assigned", icon: User }
      : issue.status === "assigned"
        ? { label: "Start work", next: "in_progress", icon: RefreshCw }
        : issue.status === "in_progress"
          ? { label: "Mark resolved", next: "resolved", icon: Radio }
          : issue.status === "resolved"
            ? { label: "Verify fix", next: "verified", icon: ShieldAlert }
            : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => router.back()} aria-label="Go back">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <IssueTypeIcon type={issue.issue_type} />
        <div>
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
            {humanize(issue.issue_type)}
          </h1>
          <p className="text-sm text-muted-foreground">Report #{issue.id}</p>
        </div>
        <span
          className={`ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${status.pill}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${status.dot ?? "bg-current"}`} />
          {status.label}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main column */}
        <div className="space-y-6 lg:col-span-2">
          {imageUrl ? (
            <div className="overflow-hidden rounded-xl border">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl} alt={humanize(issue.issue_type)} className="h-64 w-full object-cover" />
            </div>
          ) : (
            <div className="flex h-48 items-center justify-center rounded-xl border bg-muted/40">
              <p className="text-sm text-muted-foreground">No photo attached</p>
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Report details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <span
                  className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${sev.pill}`}
                >
                  {sev.label} priority
                </span>
                {issue.review_required && (
                  <Badge
                    variant="outline"
                    className="border-orange-200 bg-orange-50 text-orange-700"
                  >
                    Review required
                  </Badge>
                )}
                <Badge variant="secondary" className="gap-1.5">
                  <Crosshair className="h-3 w-3" />
                  Detection {(issue.confidence * 100).toFixed(0)}%
                </Badge>
              </div>

              {issue.description ? (
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Description
                  </p>
                  <p className="text-sm leading-relaxed">{issue.description}</p>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No description provided.</p>
              )}

              <Separator />

              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Detection confidence
                  </p>
                  <div className="flex items-center gap-3">
                    <Progress
                      value={Math.round(issue.confidence * 100)}
                      className="flex-1"
                    />
                    <span className="text-sm font-semibold">
                      {(issue.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                <div>
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Reported on
                  </p>
                  <p className="text-sm font-medium">{formatDate(issue.created_at)}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {similarIssues.length > 0 && (
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base">Similar recent reports</CardTitle>
                <Badge variant="secondary">{similarQuery.data?.count ?? similarIssues.length} found</Badge>
              </CardHeader>
              <CardContent className="space-y-2">
                {similarIssues.map((s, i) => (
                  <Link
                    key={i}
                    href={`/issues/${s.issue_id}`}
                    className="flex items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40"
                  >
                    <IssueTypeIcon type={s.issue_type} className="h-4 w-4" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{humanize(s.issue_type)}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {s.description || `Report #${s.issue_id}`}
                      </p>
                    </div>
                    <Badge variant="outline" className="shrink-0">
                      {(s.similarity * 100).toFixed(0)}% match
                    </Badge>
                  </Link>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {nextAction && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Actions</CardTitle>
              </CardHeader>
              <CardContent>
                <Button
                  className="w-full gap-2"
                  onClick={async () => {
                    try {
                      await apiFetch(`/api/v1/issues/${issueId}/status`, {
                        method: "PATCH",
                        body: JSON.stringify({ status: nextAction.next }),
                      });
                      window.location.reload();
                    } catch {
                      /* status change failed */
                    }
                  }}
                >
                  <nextAction.icon className="h-4 w-4" />
                  {nextAction.label}
                </Button>
                <Button asChild variant="outline" className="mt-2 w-full gap-2">
                  <Link href="/map">
                    <MapPin className="h-4 w-4" />
                    View on map
                  </Link>
                </Button>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <DetailRow label="Report ID" value={`#${issue.id}`} />
              <DetailRow label="Zone" value={`Ward ${issue.ward_id}`} />
              <DetailRow label="Latitude" value={issue.latitude.toFixed(5)} mono />
              <DetailRow label="Longitude" value={issue.longitude.toFixed(5)} mono />
              <DetailRow label="Reported by" value={`User #${issue.reporter_id}`} />
              {issue.assigned_to && (
                <DetailRow
                  label="Assigned to"
                  value={issue.engineer_name || `Engineer #${issue.assigned_to}`}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <TimelineItem
                  color="bg-sky-500"
                  title="Reported"
                  subtitle={formatDate(issue.created_at)}
                  active
                />
                {issue.status !== "reported" && (
                  <TimelineItem
                    color="bg-violet-500"
                    title="Assigned"
                    subtitle="Assigned to a field team"
                    active={issue.status !== "reported"}
                  />
                )}
                {(issue.status === "in_progress" || issue.status === "resolved") && (
                  <TimelineItem color="bg-amber-500" title="Work started" active />
                )}
                {(issue.status === "resolved" || issue.status === "verified") && (
                  <TimelineItem color="bg-emerald-500" title="Resolved" active />
                )}
                {issue.status === "verified" && (
                  <TimelineItem color="bg-emerald-500" title="Verified" active />
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function TimelineItem({
  color,
  title,
  subtitle,
  active,
}: {
  color: string;
  title: string;
  subtitle?: string;
  active: boolean;
}) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <span
          className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${color} ${
            active ? "" : "opacity-30"
          }`}
        />
        {active && <span className="mt-1 h-full w-px bg-border" />}
      </div>
      <div className="pb-1">
        <p className={`text-sm font-medium ${active ? "" : "text-muted-foreground"}`}>
          {title}
        </p>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
    </div>
  );
}
