export const STATUS_META: Record<
  string,
  { label: string; dot: string; pill: string }
> = {
  reported: {
    label: "Reported",
    dot: "bg-sky-500",
    pill: "bg-sky-50 text-sky-700 ring-sky-600/20",
  },
  assigned: {
    label: "Assigned",
    dot: "bg-violet-500",
    pill: "bg-violet-50 text-violet-700 ring-violet-600/20",
  },
  in_progress: {
    label: "In Progress",
    dot: "bg-amber-500",
    pill: "bg-amber-50 text-amber-700 ring-amber-600/20",
  },
  resolved: {
    label: "Resolved",
    dot: "bg-emerald-500",
    pill: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  },
}

export function humanize(value: string): string {
  if (!value) return value
  return value
    .replace(/[_\-]+/g, " ")
    .replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

export function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .map((w) => w[0])
      .slice(0, 2)
      .join("")
      .toUpperCase() || "U"
  )
}

export function formatDate(iso: string): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

export function formatDateShort(iso: string): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })
}

export function severityMeta(severity: number): {
  label: string
  pill: string
} {
  if (severity >= 4)
    return {
      label: "High",
      pill: "bg-red-50 text-red-700 ring-red-600/20",
    }
  if (severity === 3)
    return {
      label: "Medium",
      pill: "bg-orange-50 text-orange-700 ring-orange-600/20",
    }
  return {
    label: "Low",
    pill: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  }
}

export const STATUS_ORDER = ["reported", "assigned", "in_progress", "resolved"]

export const TYPE_META: Record<
  string,
  { label: string; chip: string; color: string }
> = {
  pothole: { label: "Pothole", chip: "bg-red-50 text-red-600", color: "#dc2626" },
  garbage: { label: "Garbage", chip: "bg-amber-50 text-amber-600", color: "#d97706" },
  debris: { label: "Debris", chip: "bg-violet-50 text-violet-600", color: "#7c3aed" },
}

export function typeMeta(type: string): { label: string; chip: string; color: string } {
  return (
    TYPE_META[type] ?? {
      label: humanize(type),
      chip: "bg-slate-100 text-slate-600",
      color: "#64748b",
    }
  )
}

export const PAGE_TITLES: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "Dashboard", subtitle: "Live overview of civic issues across Vadodara" },
  "/issues": { title: "Issue Reports", subtitle: "Track, review, and manage reported issues" },
  "/map": { title: "City Map", subtitle: "Geospatial view of active issues" },
  "/engineers": { title: "Field Teams", subtitle: "Workload and availability of field engineers" },
  "/admin/review": { title: "Review Queue", subtitle: "Approve, reject, or reclassify AI-flagged issues" },
  "/admin/users": { title: "Users", subtitle: "View and manage all registered accounts" },
  "/settings": { title: "Settings", subtitle: "Manage your account and preferences" },
}
