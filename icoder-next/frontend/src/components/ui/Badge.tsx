import type { HTMLAttributes } from "react";
import { cn } from "../../design/cn";

type Tone = "neutral" | "teal" | "warn";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface text-muted border-line",
  teal: "bg-teal-50 text-teal-600 border-teal-100",
  warn: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "neutral", className, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...rest}
    />
  );
}
