import { Component, type ReactNode } from 'react';

import { useT } from '../../i18n';

interface Props { children: ReactNode; fallback?: ReactNode }
interface State { hasError: boolean; error?: Error; stack?: string | null }

function DefaultFallback({ error, stack }: { error?: Error; stack?: string | null }) {
  const t = useT();
  const isDev = typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV;
  return (
    <div className="flex items-center justify-center p-8">
      <div className="text-center max-w-xl">
        <p className="text-sm text-muted-foreground mb-2">{t.errorBoundaryLoadFailed}</p>
        {isDev && error && (
          <details className="mt-3 text-left text-xs text-destructive bg-destructive/5 border border-destructive/30 rounded-lg p-3">
            <summary className="cursor-pointer font-medium mb-1">{error.name}: {error.message}</summary>
            {stack && <pre className="whitespace-pre-wrap break-words mt-2 text-[10px] text-muted-foreground">{stack}</pre>}
          </details>
        )}
        <button
          onClick={() => { window.location.reload(); }}
          className="mt-3 text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {t.errorBoundaryRetry}
        </button>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, stack: error?.stack ?? null };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    console.error('[ErrorBoundary] render threw:', error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return <DefaultFallback error={this.state.error} stack={this.state.stack} />;
    }
    return this.props.children;
  }
}
