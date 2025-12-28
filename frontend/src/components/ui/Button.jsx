import React from 'react';
import { cn } from '../../utils/class-names';
import { Loader2 } from 'lucide-react';

const Button = React.forwardRef(({ className, variant = 'primary', size = 'default', loading = false, children, ...props }, ref) => {
  const variants = {
    primary: "bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20 shadow-sm",
    secondary: "bg-white border border-slate-300 text-slate-700 hover:bg-slate-50",
    danger: "bg-red-600 hover:bg-red-700 text-white shadow-sm",
    ghost: "hover:bg-slate-100 text-slate-600 hover:text-slate-900",
  };

  const sizes = {
    default: "h-12 px-6 py-3 text-lg",
    sm: "h-9 px-3 text-sm",
    lg: "h-14 px-8 text-xl",
    icon: "h-10 w-10 p-2 flex items-center justify-center",
  };

  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-xl font-bold transition-all disabled:opacity-50 disabled:pointer-events-none active:scale-95",
        variants[variant],
        sizes[size],
        className
      )}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <Loader2 className="mr-2 h-5 w-5 animate-spin" />}
      {children}
    </button>
  );
});

Button.displayName = "Button";

export { Button };
