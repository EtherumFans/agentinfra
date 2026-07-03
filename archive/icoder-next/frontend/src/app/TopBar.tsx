import { Link, useLocation } from "react-router-dom";
import { useSession } from "./session";
import { useTheme } from "./theme";
import { cn } from "../design/cn";
import type { Role } from "../types";

const ROLES: Role[] = ["coder", "reviewer", "admin"];

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "切换到浅色模式" : "切换到深色模式"}
      title={dark ? "浅色模式" : "深色模式"}
      className="grid h-8 w-8 place-items-center rounded-lg border border-line text-muted transition-colors duration-fast hover:bg-surface hover:text-ink"
    >
      {dark ? (
        // Sun — click to go light
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      ) : (
        // Moon — click to go dark
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

// Minimal top bar — no persistent nav, no three-grid. Brand wordmark on the left,
// a single deployment marker, and the host-injected role (auth) on the right.
export function TopBar() {
  const { role, setRole } = useSession();
  const { pathname } = useLocation();
  const onDetail = pathname.startsWith("/agents/");
  const onQuickstart = pathname === "/quickstart";

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-panel/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-3 sm:px-6">
        <Link to="/" className="flex shrink-0 items-center gap-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-teal-600 text-sm font-bold text-white dark:bg-teal dark:text-canvas">
            iC
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-ink">iCoDer</span>
        </Link>
        <span className="hidden text-xs text-faint sm:inline">医疗收入合规 AI · 院内私有化</span>

        <div className="flex-1" />

        {onDetail && (
          <Link
            to="/"
            aria-label="返回全部智能体"
            className="shrink-0 whitespace-nowrap text-sm text-muted transition-colors hover:text-ink"
          >
            ←<span className="hidden sm:inline"> 全部智能体</span>
          </Link>
        )}

        <Link
          to="/quickstart"
          className={cn(
            "shrink-0 whitespace-nowrap text-sm transition-colors hover:text-ink",
            onQuickstart ? "text-ink" : "text-muted",
          )}
        >
          开发者
        </Link>

        <ThemeToggle />

        <label className="flex items-center gap-2 text-xs text-faint">
          <span className="hidden sm:inline">登录身份</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            aria-label="登录身份"
            className="rounded-lg border border-line bg-panel px-2 py-1 text-xs text-ink focus-visible:border-teal"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>
    </header>
  );
}
