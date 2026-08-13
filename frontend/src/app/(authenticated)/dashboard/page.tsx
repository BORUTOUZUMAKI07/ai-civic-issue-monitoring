"use client"

import Link from "next/link"
import {
  useDashboardStats,
  useIssues,
  useMe,
  useWards,
} from "@/queries/index"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { BentoCard } from "@/components/ui/bento-card"
import { NumberTicker } from "@/components/ui/number-ticker"
import { SpotlightCard } from "@/components/ui/spotlight-card"
import { IssueTypeIcon } from "@/components/shared/issue-icon"
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  CircleDot,
  Clock,
  FileText,
  LocateFixed,
  MapPin,
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
  typeMeta,
} from "@/lib/format"

const STATUS_COLORS: Record<string, string> = {
  reported: "#38bdf8",
  assigned: "#a78bfa",
  in_progress: "#fbbf24",
  resolved: "#34d399",
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
    <BentoCard className="p-5">
      <div className="flex items-center justify-between">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-muted-foreground">
            {label}
          </p>
          <NumberTicker
            value={value}
            className="mt-1.5 block text-3xl font-semibold tracking-tight"
          />
          {caption && (
            <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
              <ArrowUpRight className="h-3 w-3 text-emerald-500" />
              {caption}
            </p>
          )}
        </div>
        <div
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white shadow-sm ${chipClass}`}
        >
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </BentoCard>
  )
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ name?: string; value?: number | string }>
  label?: string | number
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-border/80 bg-card/95 px-3.5 py-2.5 text-xs shadow-lift backdrop-blur">
      <p className="font-semibold">{label}</p>
      <p className="mt-0.5 text-muted-foreground">
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
        <div className="h-44 animate-pulse rounded-2xl bg-muted" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[104px] animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="h-80 animate-pulse rounded-xl bg-muted lg:col-span-5" />
          <div className="h-80 animate-pulse rounded-xl bg-muted lg:col-span-7" />
        </div>
      </div>
    )
  }

  const total = stats?.total_issues ?? 0
  const byStatus = stats?.by_status ?? {}
  const resolvedCount = byStatus.resolved ?? 0
  const resolutionRate = total > 0 ? Math.round((resolvedCount / total) * 100) : 0

  const statusData = STATUS_ORDER.filter((s) => (byStatus[s] ?? 0) > 0).map(
    (s) => ({ name: STATUS_META[s].label, value: byStatus[s] })
  )

  const typeData = Object.entries(stats?.by_type ?? {})
    .map(([name, value]) => ({ name: typeMeta(name).label, key: name, value }))
    .sort((a, b) => b.value - a.value)

  const wardData = (stats?.by_ward ?? [])
    .slice()
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)

  const maxWard = Math.max(1, ...wardData.map((w) => w.count))
  const rankStyles = [
    "bg-gradient-to-br from-indigo-500 to-violet-500 text-white",
    "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300",
    "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300",
  ]

  const recent = (issuesData?.items ?? []).slice(0, 6)
  const hasData = total > 0

  const hour = new Date().getHours()
  const greeting =
    hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"
  const firstName = user?.full_name?.split(" ")[0]

  return (
    <div className="space-y-6">
      {/* Hero band */}
      <SpotlightCard className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-950 via-blue-950 to-violet-950 px-6 py-8 text-white shadow-lift ring-1 ring-inset ring-white/10 sm:px-8">
        <div aria-hidden className="absolute inset-0 bg-grid-white opacity-50" />
        <div
          aria-hidden
          className="absolute -left-20 -top-24 h-72 w-72 animate-aurora rounded-full bg-indigo-500/40 blur-3xl"
        />
        <div
          aria-hidden
          className="absolute -bottom-24 right-0 h-72 w-72 animate-aurora-slow rounded-full bg-violet-500/40 blur-3xl"
        />
        <div
          aria-hidden
          className="absolute left-1/2 top-1/2 h-64 w-64 rounded-full bg-sky-500/20 blur-3xl"
        />
        <div aria-hidden className="absolute inset-0 bg-noise opacity-[0.12]" />

        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium ring-1 ring-inset ring-white/20 backdrop-blur-sm">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
              </span>
              <MapPin className="h-3 w-3" />
              Vadodara Municipal Corporation
            </p>
            <h2 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
              {firstName ? `${greeting}, ${firstName}` : greeting}
            </h2>
            <p className="mt-1.5 max-w-md text-sm text-indigo-100/90">
              Here&apos;s what&apos;s happening across the city today.
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:items-end">
            <Button asChild size="lg" className="gap-2 bg-white text-indigo-700 shadow-lg hover:bg-indigo-50">
              <Link href="/issues">
                <Plus className="h-4 w-4" />
                Report an issue
              </Link>
            </Button>
            <p className="text-xs text-indigo-100/80">
              {stats?.recent_count ?? 0} reports added this month
            </p>
          </div>
        </div>
      </SpotlightCard>

      {/* KPI cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Total Reports"
          value={total}
          icon={FileText}
          chipClass="bg-gradient-to-br from-sky-500 to-blue-600"
          caption="all time"
        />
        <KpiCard
          label="In Progress"
          value={byStatus.in_progress ?? 0}
          icon={Wrench}
          chipClass="bg-gradient-to-br from-amber-400 to-orange-500"
          caption="being worked on"
        />
        <KpiCard
          label="Assigned"
          value={byStatus.assigned ?? 0}
          icon={Users2}
          chipClass="bg-gradient-to-br from-violet-500 to-purple-600"
          caption="to field teams"
        />
        <KpiCard
          label="Resolved"
          value={resolvedCount}
          icon={CheckCircle2}
          chipClass="bg-gradient-to-br from-emerald-400 to-teal-600"
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
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Status donut */}
          <Card className="lg:col-span-5">
            <CardHeader>
              <CardTitle className="text-base">Issue Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative mx-auto h-52 max-w-xs">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={statusData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={58}
                      outerRadius={84}
                      paddingAngle={3}
                      strokeWidth={0}
                    >
                      {statusData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={
                            STATUS_COLORS[
                              entry.name.toLowerCase().replace(" ", "_")
                            ] ?? "#94a3b8"
                          }
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
              <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5">
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
                    <span className="truncate text-muted-foreground">{s.name}</span>
                    <span className="ml-auto font-semibold">{s.value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Category bar */}
          <Card className="lg:col-span-7">
            <CardHeader>
              <CardTitle className="text-base">Issues by Category</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={typeData} margin={{ left: -18, right: 8 }}>
                  <defs>
                    <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#818cf8" />
                      <stop offset="100%" stopColor="#4f46e5" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    content={<ChartTooltip />}
                    cursor={{ fill: "rgba(148,163,184,0.08)" }}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]} maxBarSize={36}>
                    {typeData.map((entry) => (
                      <Cell key={entry.key} fill="url(#barGradient)" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Top wards */}
          <Card className="lg:col-span-5">
            <CardHeader>
              <CardTitle className="text-base">Top Wards</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {wardData.map((w, idx) => (
                <div key={w.ward} className="flex items-center gap-3">
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold ${
                      rankStyles[Math.min(idx, 2)]
                    }`}
                  >
                    {idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                      <span className="truncate font-medium">{w.ward}</span>
                      <span className="text-muted-foreground">
                        {w.count} issue{w.count === 1 ? "" : "s"}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
                        style={{ width: `${(w.count / maxWard) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Recent issues */}
          <Card className="lg:col-span-7">
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Recent Issues</CardTitle>
              <Button asChild variant="ghost" size="sm" className="text-primary hover:text-primary">
                <Link href="/issues">
                  View all
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              {recent.length === 0 ? (
                <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4 animate-spin" />
                  Loading recent issues…
                </div>
              ) : (
                <div className="divide-y">
                  {recent.map((issue) => {
                    const status = STATUS_META[issue.status] ?? {
                      label: humanize(issue.status),
                      pill: "bg-muted text-muted-foreground ring-muted",
                      dot: "bg-muted",
                    }
                    const sev = severityMeta(issue.severity)
                    return (
                      <Link
                        key={issue.id}
                        href={`/issues/${issue.id}`}
                        className="group flex items-center gap-4 py-3 transition-colors hover:bg-muted/40"
                      >
                        <IssueTypeIcon type={issue.issue_type} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium group-hover:text-primary">
                            {humanize(issue.issue_type)}
                          </p>
                          <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                            <MapPin className="h-3 w-3 shrink-0" />
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
                        <span
                          className={`hidden rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset md:inline ${sev.pill}`}
                        >
                          {sev.label}
                        </span>
                      </Link>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* System health strip */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-border/80 bg-card px-5 py-3 text-xs text-muted-foreground shadow-sm">
        <span className="inline-flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          Systems operational
        </span>
        <Separator orientation="vertical" className="hidden h-4 sm:block" />
        <span className="inline-flex items-center gap-1.5">
          <CircleDot className="h-3.5 w-3.5 text-indigo-500" />
          AI classification active
        </span>
        <Separator orientation="vertical" className="hidden h-4 sm:block" />
        <span className="inline-flex items-center gap-1.5">
          <LocateFixed className="h-3.5 w-3.5" />
          Last updated just now
        </span>
        <span className="ml-auto hidden items-center gap-1.5 sm:flex">
          <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground/60" />
          {byStatus.reported ?? 0} awaiting review
        </span>
      </div>
    </div>
  )
}
