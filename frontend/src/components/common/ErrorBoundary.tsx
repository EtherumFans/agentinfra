import { Component, type ReactNode } from 'react';
import { useT } from '../../i18n';

interface Props { children: ReactNode; fallback?: ReactNode }
interface State { hasError: boolean; error?: Error }

function DefaultFallback() {
  const t = useT();
  return (
    <div className="flex items-center justify-center p-8">
      <div className="text-center">
        <p className="text-sm text-muted-foreground mb-2">{t.errorBoundaryLoadFailed}</p>
        <button
          onClick={() => { /* parent re-renders via setState below */ window.location.reload(); }}
          className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
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
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || <DefaultFallback />;
    }
    return this.props.children;
  }
}
