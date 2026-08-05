import { useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';

import { authApi } from '../services/api';
import { useT } from '../i18n';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const t = useT();
  const token = searchParams.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [done, setDone] = useState(false);

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg('');
    if (password.length < 8) { setMsg(t.resetPasswordTooShort); return; }
    if (password !== confirm) { setMsg(t.resetPasswordMismatch); return; }
    if (!token) { setMsg(t.resetPasswordNoToken); return; }
    setLoading(true);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
      setMsg(t.resetPasswordSuccess);
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || t.resetPasswordFailed);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-dvh flex items-center justify-center bg-muted/30">
      <div className="w-full max-w-sm bg-background rounded-xl shadow-sm p-6">
        <h1 className="text-lg font-semibold text-foreground mb-1">{t.resetPasswordTitle}</h1>
        <p className="text-xs text-muted-foreground mb-4">{t.resetPasswordSubtitle}</p>

        {done ? (
          <div>
            <p className="text-sm text-secondary mb-4">{msg}</p>
            <Link to="/login" className="text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground inline-block">
              {t.resetPasswordBackToLogin}
            </Link>
          </div>
        ) : (
          <form onSubmit={handleReset} className="space-y-4">
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">{t.resetPasswordNewPassword}</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder={t.resetPasswordNewPlaceholder} autoFocus
                className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            </div>
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">{t.resetPasswordConfirm}</label>
              <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
                placeholder={t.resetPasswordConfirmPlaceholder}
                className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            </div>
            {msg && <p className={`text-xs ${done ? 'text-secondary' : 'text-destructive'}`}>{msg}</p>}
            <button type="submit" disabled={loading}
              className="w-full text-sm py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {loading ? t.resetPasswordLoading : t.resetPasswordSubmit}
            </button>
            <p className="text-xs text-muted-foreground text-center">
              <Link to="/login" className="hover:underline">{t.resetPasswordBackToLogin}</Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
