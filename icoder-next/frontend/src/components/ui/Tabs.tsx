import { useRef } from "react";
import type { KeyboardEvent } from "react";
import { cn } from "../../design/cn";

export interface TabItem {
  id: string;
  label: string;
}

interface TabsProps {
  items: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
  /** When set, tabs are wired (id + aria-controls) to panels with id `${idBase}-panel-<id>`. */
  idBase?: string;
}

export function Tabs({ items, active, onChange, className, idBase }: TabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  // WAI-ARIA tab pattern: arrow keys move (and activate) between tabs, Home/End jump.
  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = items.length - 1;
    let next = -1;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = index === last ? 0 : index + 1;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = index === 0 ? last : index - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    if (next === -1) return;
    e.preventDefault();
    onChange(items[next].id);
    refs.current[next]?.focus();
  }

  return (
    <div
      className={cn("inline-flex max-w-full gap-1 overflow-x-auto rounded-lg bg-surface p-1", className)}
      role="tablist"
    >
      {items.map((it, i) => {
        const selected = it.id === active;
        return (
          <button
            key={it.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            id={idBase ? `${idBase}-tab-${it.id}` : undefined}
            aria-controls={idBase ? `${idBase}-panel-${it.id}` : undefined}
            onClick={() => onChange(it.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              "shrink-0 rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-fast",
              selected ? "bg-panel text-ink shadow-card" : "text-muted hover:text-ink",
            )}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}
