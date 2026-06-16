import { cn } from "../../design/cn";

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="加载中"
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-line border-t-teal",
        className,
      )}
    />
  );
}
