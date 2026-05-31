import { X, AlertTriangle, AlertCircle, CheckCircle } from 'lucide-react';
import { useToastStore } from '../../store';

const ICON = {
  error: AlertCircle,
  warning: AlertTriangle,
  success: CheckCircle,
};

const STYLE = {
  error: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
  success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => {
        const Icon = ICON[t.type];
        return (
          <div
            key={t.id}
            className={`flex items-start gap-2 px-4 py-3 rounded-lg border shadow-lg text-sm ${STYLE[t.type]}`}
          >
            <Icon size={16} className="shrink-0 mt-0.5" />
            <span className="flex-1 leading-snug">{t.message}</span>
            <button onClick={() => removeToast(t.id)} className="shrink-0 opacity-60 hover:opacity-100">
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
