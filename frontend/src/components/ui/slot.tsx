import * as React from "react";
import { Slot as RadixSlot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

const Slot = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, ...props }, ref) => (
    <RadixSlot ref={ref} className={cn(className)} {...props} />
  )
);
Slot.displayName = "Slot";

export { Slot };
