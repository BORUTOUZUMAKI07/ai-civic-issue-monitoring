"use client";

import { useDashboardStats, useHeatmapData, useIssues } from "@/queries/index";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, CheckCircle, Clock, MapPin, TrendingUp, Activity, Brain, Cpu } from "lucide-react";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: typeof AlertTriangle }> = {
  reported: { label: "Reported", color: "text-blue-500", icon: MapPin },
  assigned: { label: "Assigned", color: "text-purple-500", icon: Clock },
  in_progress: { label: "In Progress", color: "text-yellow-500", icon: Activity },
  resolved: { label: "Resolved", color: "text-green-500", icon: CheckCircle },
};

const TYPE_COLORS = ["#ef4444", "#f59e0b", "#3b82f6", "#06b6d4", "#8b5cf6", "#f97316", "#14b8a6"];

const severityBadge = (s: number) => {
  if (s >= 4) return <Badge className="bg-red-100 text-red-700 border-red-200">S{s}</Badge>;
  if (s === 3) return <Badge className="bg-orange-100 text-orange-700 border-orange-200">S{s}</Badge>;
  if (s === 2) return <Badge className="bg-yellow-100 text-yellow-700 border-yellow-200">S{s}</Badge>;
  return <Badge className="bg-green-100 text-green-700 border-green-200">S{s}</Badge>;
};

const statusBadge = (s: string) => {
  const colors: Record<string, string> = {
    reported: "bg-blue-100 text-blue-700 border-blue-200",
    assigned: "bg-purple-100 text-purple-700 border-purple-200",
    in_progress: "bg-yellow-100 text-yellow-700 border-yellow-200",
    resolved: "bg-green-100 text-green-700 border-green-200",
  };
  return <Badge className={colors[s] || ""}>{s.replace("_", " ")}</Badge>;
};

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: heatmap } = useHeatmapData();
  const { data: issuesData } = useIssues({ limit: 8 });
  const [modelInfo, setModelInfo] = useState<{ model_exists: boolean; model_size_mb: number; classes: string[]; device: string } | null>(null);

  useEffect(() => {
    apiFetch("/api/v1/ml/info").then((data) => setModelInfo(data as { model_exists: boolean; model_size_mb: number; classes: string[]; device: string })).catch(() => {});
  }, []);

  if (statsLoading) {
    return (
      <div className="space-y-6 p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="h-20 bg-muted rounded animate-pulse" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const totalIssues = stats?.total_issues || 0;
  const resolvedCount = stats?.by_status?.resolved || 0;
  const resolutionRate = totalIssues > 0 ? ((resolvedCount / totalIssues) * 100).toFixed(0) : "0";
  const recentCount = stats?.recent_count || 0;

  const statusData = stats?.by_status
    ? Object.entries(stats.by_status).map(([name, value]) => ({
        name: name.replace("_", " "),
        value,
        fullName: name,
      }))
    : [];

  const typeData = stats?.by_type
    ? Object.entries(stats.by_type).map(([name, value]) => ({
        name: name.replace("_", " "),
        value,
      }))
    : [];

  const wardData = stats?.by_ward || [];

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">Overview of civic issues across Vadodara</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <TrendingUp className="h-4 w-4" />
          {recentCount} issues this month
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => {
          const Icon = cfg.icon;
          const count = stats?.by_status?.[key] || 0;
          return (
            <Card key={key} className="hover:shadow-md transition-shadow">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">{cfg.label}</p>
                    <p className="text-3xl font-bold mt-1">{count}</p>
                  </div>
                  <div className={`h-10 w-10 rounded-lg bg-muted flex items-center justify-center ${cfg.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                </div>
                {key === "reported" && (
                  <div className="mt-2 text-xs text-muted-foreground">
                    {resolutionRate}% resolution rate
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status Pie */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By Status</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={statusData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={4} dataKey="value">
                  {statusData.map((_, i) => (
                    <Cell key={i} fill={["#3b82f6", "#8b5cf6", "#eab308", "#22c55e"][i % 4]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Type Bar */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By Category</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={typeData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {typeData.map((_, i) => (
                    <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Ward Bar */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By Ward</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={wardData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="ward" width={80} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Recent Issues */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Issues</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {issuesData?.items?.slice(0, 6).map((issue) => (
              <div key={issue.id} className="flex items-center justify-between p-3 rounded-lg border border-border/50 hover:bg-muted/50 transition-colors">
                <div className="flex items-center gap-3">
                  <div className={`h-2 w-2 rounded-full ${STATUS_CONFIG[issue.status]?.color || "bg-gray-400"}`} />
                  <div>
                    <span className="text-sm font-medium capitalize">{issue.issue_type.replace("_", " ")}</span>
                    <span className="text-xs text-muted-foreground ml-2">
                      Ward {issue.ward_id} &middot; {new Date(issue.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {severityBadge(issue.severity)}
                  {statusBadge(issue.status)}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ML Model Info */}
      {modelInfo && (
        <Card className="border-primary/20">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Brain className="h-4 w-4" /> ML Classification Model
              {modelInfo.model_exists ? (
                <Badge className="bg-green-100 text-green-700 border-0 text-xs">Active</Badge>
              ) : (
                <Badge className="bg-red-100 text-red-700 border-0 text-xs">Not Loaded</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">Model</p>
                <p className="font-semibold text-sm flex items-center gap-1"><Cpu className="h-3 w-3" /> MobileNetV2</p>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">Size</p>
                <p className="font-semibold text-sm">{modelInfo.model_size_mb} MB</p>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">Classes</p>
                <p className="font-semibold text-sm">{modelInfo.classes.length}-class</p>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">Device</p>
                <p className="font-semibold text-sm uppercase">{modelInfo.device}</p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {modelInfo.classes.map((c) => (
                <Badge key={c} variant="outline" className="text-xs">{c}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
