"use client"

import Link from "next/link"
import { useDashboardStats, useIssues, useMe, useWards } from "@/queries/index"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Plus,
  Users2,
  Wrench,
} from "lucide-react"
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import {
  STATUS_META,
  STATUS_ORDER,
  formatDateShort,
  humanize,
  severityMeta,
} from "@/lib/format"

const TYPE_COLORS = [
  "#2563eb",
  "#7c3aed",
  "#0ea5e9",
  "#f59e0b",
  "#10b981",
  "#f43f5e",
  "#64748b",
]

const STATUS_COLORS: Record<string, string> = {
  reported: "#0ea5e9",
  assigned: "#8b5cf6",
  in_progress: "#f59e0b",
  resolved: "#10b981",
}

function KpiCard({
  label,
  value,
  icon: Icon,
  chipClass,
  caption,
}: {
  label: string
  value: number
  icon: typeof FileText
  chipClass: string
  caption?: string
}) {
  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="flex items-center justify-between p-5">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          <p className="mt-1.5 text-3xl font-semibold tracking-tight">{value}</p>
          {caption && (
            <p className="mt-1 text-xs text-muted-foreground">{caption}</p>
          )}
        </div>
        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${chipClass}`}>
          <Icon className="h-5 w-5" />
        </div>
      </CardContent>
    </Card>
  )
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-xs shadow-lg">
      <p className="font-medium">{label}</p>
      <p className="text-muted-foreground">
        {payload[0].name}:{" "}
        <span className="font-semibold text-foreground">{payload[0].value}</span>
      </p>
    </div>
  )
}

export default function DashboardPage() {
  const { data: stats, isLoading } = useDashboardStats()
  const { data: issuesData } = useIssues({ limit: 6 })
  const { data: wards } = useWards()
  const { data: user } = useMe()

  const wardName = (id: number) =>
    wards?.find((w) => w.id === id)?.name ?? `Ward ${id}`

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[104px] animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      </div>
    )
  }

  const total = stats?.total_issues ?? 0
  const byStatus = stats?.by_status ?? {}
  const resolvedCount = byStatus.resolved ?? 0
  const resolutionRate = total > 0 ? Math.round((resolvedCount / total) * 100) : 0

  const statusData = STATUS_ORDER.filter((s) => (byStatus[s] ?? 0) > 0).map(
    (s) => ({
      name: STATUS_META[s].label,
      value: byStatus[s],
    })
  )

  const typeData = Object.entries(stats?.by_type ?? {})
    .map(([name, value]) => ({ name: humanize(name), value }))
    .sort((a, b) => b.value - a.value)

  const wardData = (stats?.by_ward ?? [])
    .slice()
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)

  const maxWard = Math.max(1, ...wardData.map((w) => w.count))

  const recent = (issuesData?.items ?? []).slice(0, 6)
  const hasData = total > 0

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
            {user?.full_name?.split(" ")[0]
              ? `Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, ${user.full_name.split(" ")[0]}`
              : "Welcome back"}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Here&apos;s what&apos;s happening across the city today.
          </p>
        </div>
        <Link
          href="/issues"
          className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Report an issue
        </Link>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Total Reports"
          value={total}
          icon={FileText}
          chipClass="bg-blue-50 text-blue-600"
          caption={`${stats?.recent_count ?? 0} added this month`}
        />
        <KpiCard
          label="In Progress"
          value={byStatus.in_progress ?? 0}
          icon={Wrench}
          chipClass="bg-amber-50 text-amber-600"
        />
        <KpiCard
          label="Assigned"
          value={byStatus.assigned ?? 0}
          icon={Users2}
          chipClass="bg-violet-50 text-violet-600"
        />
        <KpiCard
          label="Resolved"
          value={resolvedCount}
          icon={CheckCircle2}
          chipClass="bg-emerald-50 text-emerald-600"
          caption={`${resolutionRate}% resolution rate`}
        />
      </div>

      {!hasData ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <FileText className="h-7 w-7 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-base font-semibold">No issues reported yet</h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              Once citizens start reporting issues, the dashboard will populate
              with live statistics and trends.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Charts */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Status donut */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Issue Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={statusData}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={58}
                        outerRadius={82}
                        paddingAngle={3}
                        strokeWidth={0}
                      >
                        {statusData.map((entry) => (
                          <Cell
                            key={entry.name}
                            fill={STATUS_COLORS[entry.name.toLowerCase().replace(" ", "_")] ?? "#94a3b8"}
                          />
                        ))}
                      </Pie>
                      <Tooltip content={<ChartTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-3xl font-semibold tracking-tight">
                      {total}
                    </span>
                    <span className="text-xs text-muted-foreground">total</span>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {statusData.map((s) => (
                    <div key={s.name} className="flex items-center gap-2 text-sm">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{
                          backgroundColor:
                            STATUS_COLORS[s.name.toLowerCase().replace(" ", "_")] ??
                            "#94a3b8",
                        }}
                      />
                      <span className="text-muted-foreground">{s.name}</span>
                      <span className="ml-auto font-semibold">{s.value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Category bar */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By Category</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={228}>
                  <BarChart data={typeData} margin={{ left: -18 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(148,163,184,0.08)" }} />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={28}>
                      {typeData.map((_, i) => (
                        <Cell key={i} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Ward ranking */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Top Wards</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {wardData.map((w) => (
                    <div key={w.ward}>
                      <div className="mb-1 flex items-center justify-between text-sm">
                        <span className="font-medium">{w.ward}</span>
                        <span className="text-muted-foreground">{w.count}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-blue-600"
                          style={{ width: `${(w.count / maxWard) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Recent issues */}
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Recent Issues</CardTitle>
              <Link
                href="/issues"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              >
                View all
                <ArrowRight className="h-4 w-4" />
              </Link>
            </CardHeader>
            <CardContent>
              {recent.length === 0 ? (
                <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading recent issues…
                </div>
              ) : (
                <div className="divide-y">
                  {recent.map((issue) => {
                    const status = STATUS_META[issue.status] ?? {
                      label: humanize(issue.status),
                      pill: "bg-muted text-muted-foreground ring-muted",
                    }
                    const sev = severityMeta(issue.severity)
                    return (
                      <Link
                        key={issue.id}
                        href={`/issues/${issue.id}`}
                        className="flex items-center gap-4 py-3 transition-colors hover:bg-muted/40"
                      >
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                          <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">
                            {humanize(issue.issue_type)}
                          </p>
                          <p className="truncate text-xs text-muted-foreground">
                            {wardName(issue.ward_id)} · {formatDateShort(issue.created_at)}
                          </p>
                        </div>
                        <span className="hidden items-center gap-1.5 sm:flex">
                          <span className={`h-2 w-2 rounded-full ${status.dot}`} />
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${status.pill}`}
                          >
                            {status.label}
                          </span>
                        </span>
                        <Badge className={`border-0 ring-1 ring-inset ${sev.pill}`}>
                          {sev.label}
                        </Badge>
                      </Link>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* System health strip */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border bg-card px-5 py-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          Systems operational
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" />
          Last updated just now
        </span>
      </div>
    </div>
  )
}
