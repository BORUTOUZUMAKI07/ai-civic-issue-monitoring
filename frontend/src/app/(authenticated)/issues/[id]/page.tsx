"use client";

import { use } from "react";
import { useIssue } from "@/queries/index";
import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, MapPin, Clock, Brain, Target, BarChart3 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useEffect } from "react";

const severityBadge = (s: number) => {
  const labels = ["", "Minimal", "Low", "Medium", "High", "Critical"];
  const colors = ["", "bg-green-100 text-green-700", "bg-yellow-100 text-yellow-700", "bg-orange-100 text-orange-700", "bg-red-100 text-red-700", "bg-red-600 text-white"];
  return <Badge className={`${colors[s] || ""} border-0 text-sm`}>Severity {s} — {labels[s]}</Badge>;
};

const statusBadge = (s: string) => {
  const colors: Record<string, string> = {
    reported: "bg-blue-100 text-blue-700",
    assigned: "bg-purple-100 text-purple-700",
    in_progress: "bg-amber-100 text-amber-700",
    resolved: "bg-green-100 text-green-700",
  };
  return <Badge className={`${colors[s] || "bg-gray-100 text-gray-700"} border-0`}>{s.replace("_", " ")}</Badge>;
};

export default function IssueDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const issueId = parseInt(id);
  const { data: issue, isLoading } = useIssue(issueId);
  const [similar, setSimilar] = useState<{ issue_id: number; similar_issues: unknown[]; rag_context: string; count: number } | null>(null);
  const [loadingSimilar, setLoadingSimilar] = useState(false);
  const [statusUpdate, setStatusUpdate] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!issueId) return;
    setLoadingSimilar(true);
    apiFetch(`/api/v1/issues/similar/${issueId}`).then((data) => {
      setSimilar(data as { issue_id: number; similar_issues: unknown[]; rag_context: string; count: number });
    }).catch(() => {}).finally(() => setLoadingSimilar(false));
  }, [issueId]);

  const handleStatusUpdate = async (newStatus: string) => {
    setStatusUpdate(newStatus);
    try {
      await apiFetch(`/api/v1/issues/${issueId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      window.location.reload();
    } catch {
      setStatusUpdate(null);
    }
  };

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <div className="h-8 bg-muted rounded animate-pulse w-48" />
        <div className="h-64 bg-muted rounded animate-pulse" />
      </div>
    );
  }

  if (!issue) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">Issue not found.</p>
        <Link href="/issues"><Button variant="link">Back to Issues</Button></Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold capitalize">{issue.issue_type.replace("_", " ")}</h1>
          <p className="text-sm text-muted-foreground">Issue #{issue.id}</p>
        </div>
      </div>

      {/* Status & Classification */}
      <div className="flex flex-wrap gap-3">
        {statusBadge(issue.status)}
        {severityBadge(issue.severity)}
        {issue.review_required && <Badge className="bg-orange-100 text-orange-700 border-0">Needs Review</Badge>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Info */}
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Brain className="h-4 w-4" /> AI Classification
                <Badge variant="outline" className="ml-auto text-xs font-mono">MobileNetV2</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">Category</p>
                  <p className="font-semibold capitalize">{issue.issue_type.replace("_", " ")}</p>
                </div>
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">Confidence</p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${issue.confidence * 100}%` }} />
                    </div>
                    <span className="font-semibold text-sm">{(issue.confidence * 100).toFixed(1)}%</span>
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">Model</p>
                  <p className="font-semibold text-sm">MobileNetV2 (4-class)</p>
                </div>
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">Reported</p>
                  <p className="font-semibold text-sm">{new Date(issue.created_at).toLocaleString()}</p>
                </div>
              </div>
              {issue.description && (
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">Description</p>
                  <p className="text-sm">{issue.description}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* RAG Context */}
          {similar && similar.rag_context && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" /> RAG Analysis
                  <Badge variant="outline" className="ml-auto text-xs">{similar.count} similar</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-sm text-muted-foreground whitespace-pre-wrap bg-muted/30 p-4 rounded-lg font-mono text-xs leading-relaxed">
                  {similar.rag_context}
                </pre>
              </CardContent>
            </Card>
          )}

          {/* Similar Issues */}
          {similar && similar.similar_issues && similar.similar_issues.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Similar Issues Found</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(similar.similar_issues as Array<{ issue_id: number; description: string; similarity: number; issue_type: string }>).
                    map((s, i) => (
                    <Link key={i} href={`/issues/${s.issue_id}`}>
                      <div className="p-3 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors cursor-pointer">
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="text-sm font-medium capitalize">{s.issue_type?.replace("_", " ")}</span>
                            <span className="text-xs text-muted-foreground ml-2">{s.description?.substring(0, 60)}...</span>
                          </div>
                          <Badge variant="outline" className="text-xs">{(s.similarity * 100).toFixed(0)}% match</Badge>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {issue.status === "reported" && (
                <Button className="w-full" onClick={() => handleStatusUpdate("assigned")} disabled={statusUpdate === "assigned"}>
                  Assign to Engineer
                </Button>
              )}
              {issue.status === "assigned" && (
                <Button className="w-full" onClick={() => handleStatusUpdate("in_progress")} disabled={statusUpdate === "in_progress"}>
                  Start Working
                </Button>
              )}
              {issue.status === "in_progress" && (
                <Button className="w-full" onClick={() => handleStatusUpdate("resolved")} disabled={statusUpdate === "resolved"}>
                  Mark Resolved
                </Button>
              )}
              {issue.status === "resolved" && (
                <Button className="w-full" onClick={() => handleStatusUpdate("verified")} disabled={statusUpdate === "verified"}>
                  Verify Fix
                </Button>
              )}
              <Link href="/map" className="block">
                <Button variant="outline" className="w-full gap-2">
                  <MapPin className="h-4 w-4" /> View on Map
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Issue ID</span>
                <span className="font-medium">#{issue.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Latitude</span>
                <span className="font-medium font-mono">{issue.latitude.toFixed(6)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Longitude</span>
                <span className="font-medium font-mono">{issue.longitude.toFixed(6)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Reporter</span>
                <span className="font-medium">#{issue.reporter_id}</span>
              </div>
              {issue.assigned_to && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Assigned To</span>
                  <span className="font-medium">{issue.engineer_name || `Engineer #${issue.assigned_to}`}</span>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Clock className="h-4 w-4" /> Timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex gap-3">
                  <div className="h-2 w-2 rounded-full bg-blue-500 mt-1.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium">Reported</p>
                    <p className="text-xs text-muted-foreground">{new Date(issue.created_at).toLocaleString()}</p>
                  </div>
                </div>
                {issue.status !== "reported" && (
                  <div className="flex gap-3">
                    <div className="h-2 w-2 rounded-full bg-purple-500 mt-1.5 shrink-0" />
                    <div>
                      <p className="text-sm font-medium">Assigned</p>
                      <p className="text-xs text-muted-foreground">Auto-assigned by AI</p>
                    </div>
                  </div>
                )}
                {(issue.status === "in_progress" || issue.status === "resolved") && (
                  <div className="flex gap-3">
                    <div className="h-2 w-2 rounded-full bg-yellow-500 mt-1.5 shrink-0" />
                    <div>
                      <p className="text-sm font-medium">In Progress</p>
                      <p className="text-xs text-muted-foreground">Work started</p>
                    </div>
                  </div>
                )}
                {issue.status === "resolved" && (
                  <div className="flex gap-3">
                    <div className="h-2 w-2 rounded-full bg-green-500 mt-1.5 shrink-0" />
                    <div>
                      <p className="text-sm font-medium">Resolved</p>
                      <p className="text-xs text-muted-foreground">Issue fixed</p>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
