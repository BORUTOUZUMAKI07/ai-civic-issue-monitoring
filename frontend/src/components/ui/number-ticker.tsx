"use client"

import * as React from "react"
import {
  animate,
  motion,
  useMotionValue,
  useTransform,
} from "motion/react"
import { cn } from "@/lib/utils"

export function NumberTicker({
  value,
  className,
  delay = 0,
  duration = 1.4,
}: {
  value: number
  className?: string
  delay?: number
  duration?: number
}) {
  const motionValue = useMotionValue(0)

  React.useEffect(() => {
    const controls = animate(motionValue, value, {
      delay,
      duration,
      ease: "easeOut",
    })
    return () => controls.stop()
  }, [motionValue, value, delay, duration])

  const display = useTransform(motionValue, (v) => Math.round(v).toLocaleString())

  return (
    <motion.span className={cn("tabular-nums", className)}>{display}</motion.span>
  )
}
