import { Skeleton } from "@/components/ui/skeleton"

export default function Loading() {
  return (
    <div className="flex min-h-screen">
      <div className="hidden md:flex w-64 flex-col gap-4 p-4 border-r">
        <Skeleton className="h-8 w-32" />
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
      <div className="flex-1 p-6">
        <Skeleton className="h-12 w-full mb-6" />
        <Skeleton className="h-64 w-full" />
      </div>
    </div>
  )
}
