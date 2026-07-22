import { Skeleton } from "@/components/ui/skeleton"

export default function Loading() {
  return (
    <div className="p-6 space-y-6">
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-[500px] rounded-xl" />
    </div>
  )
}
