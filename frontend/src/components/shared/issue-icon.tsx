import {
  CircleDot,
  Trash2,
  BrickWall,
  MapPin,
  type LucideIcon,
} from "lucide-react"
import { typeMeta } from "@/lib/format"

const TYPE_ICONS: Record<string, LucideIcon> = {
  pothole: CircleDot,
  garbage: Trash2,
  debris: BrickWall,
}

export function IssueTypeIcon({
  type,
  className,
}: {
  type: string
  className?: string
}) {
  const Icon = TYPE_ICONS[type] ?? MapPin
  const meta = typeMeta(type)
  return (
    <span
      className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${meta.chip}`}
    >
      <Icon className={className ?? "h-5 w-5"} />
    </span>
  )
}

export { TYPE_ICONS }
