import type { ReactNode } from "react";
import { Card, CardBody } from "./Card";

// A calm, centered placeholder for "nothing here yet" — not an error. Optional action
// (e.g. a refresh link) renders below the hint.
export function EmptyState({
  title,
  hint,
  action,
  className,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardBody className="flex flex-col items-center gap-2 py-12 text-center">
        <span
          aria-hidden="true"
          className="grid h-10 w-10 place-items-center rounded-xl2 bg-surface text-faint"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <path d="M3 9h18M9 21V9" />
          </svg>
        </span>
        <p className="text-sm font-semibold text-ink">{title}</p>
        {hint && <p className="max-w-sm text-sm leading-relaxed text-muted">{hint}</p>}
        {action && <div className="mt-1">{action}</div>}
      </CardBody>
    </Card>
  );
}
