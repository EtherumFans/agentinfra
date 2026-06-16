import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Card, CardBody } from "./ui/Card";
import { Button } from "./ui/Button";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

// Render-time crash net: an error thrown anywhere in the routed tree would otherwise
// blank the whole SPA. This catches it and shows a calm, recoverable panel instead —
// the same trust posture as ErrorState, but for render failures (which ErrorState,
// used only in fetch catch-blocks, never sees). Recovery is a full reload, which
// guarantees the boundary and all stale state are cleared.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Console only — no external telemetry (data 不出院). In-hospital diagnostics read this.
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="mx-auto max-w-lg py-16">
        <Card>
          <CardBody className="flex flex-col items-start gap-3">
            <div className="flex items-start gap-3">
              <span
                aria-hidden="true"
                className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-300"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </span>
              <div role="alert">
                <p className="text-sm font-semibold text-ink">页面出错了</p>
                <p className="mt-1 text-sm leading-relaxed text-muted">
                  界面渲染时遇到未预期的错误。可重新加载本页；若反复出现，请联系院内 iCoDer 管理员。
                </p>
                {error.message && (
                  <p className="mt-2 break-all font-mono text-xs text-faint">{error.message}</p>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
                重新加载
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { window.location.href = "/"; }}>
                返回首页
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }
}
