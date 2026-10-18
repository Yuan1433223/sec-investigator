import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold font-mono transition-colors",
  {
    variants: {
      variant: {
        default: "bg-white/10 text-zinc-300",
        critical: "bg-[#ef4444]/15 text-[#ef4444]",
        high: "bg-[#f97316]/15 text-[#f97316]",
        medium: "bg-[#eab308]/15 text-[#eab308]",
        low: "bg-[#22c55e]/15 text-[#22c55e]",
        info: "bg-[#3b82f6]/15 text-[#3b82f6]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
