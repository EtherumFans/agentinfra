import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../design/cn";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANTS: Record<Variant, string> = {
  // Solid fill needs AA text contrast: in light, white on teal-600 (#0c7a6f) = 5.2:1;
  // in dark, the brightened teal carries dark canvas text = 7.6:1. Plain `bg-teal`
  // (#0f9d8f) fails white text at 3.4:1, so it's reserved for borders/bars/tints.
  primary:
    "bg-teal-600 text-white border border-teal-600 hover:bg-teal-700 hover:border-teal-700 " +
    "dark:bg-teal dark:text-canvas dark:border-teal dark:hover:bg-teal-600 dark:hover:border-teal-600",
  secondary: "bg-panel text-teal-600 border border-teal hover:bg-teal-50",
  ghost: "bg-transparent text-muted border border-transparent hover:bg-surface hover:text-ink",
};

const SIZES: Record<Size, string> = {
  sm: "text-xs px-3 py-1.5",
  md: "text-sm px-4 py-2",
};

export function Button({ variant = "primary", size = "md", className, ...rest }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium",
        "transition-colors duration-fast disabled:opacity-50 disabled:cursor-not-allowed",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    />
  );
}
