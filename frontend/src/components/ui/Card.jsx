import React from 'react';
import { cn } from '../../utils/class-names';

const Card = React.forwardRef(({ className, children, ...props }, ref) => {
  return (
    <div
      ref={ref}
      className={cn(
        "bg-white border border-slate-200 rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
});

Card.displayName = "Card";

export { Card };
