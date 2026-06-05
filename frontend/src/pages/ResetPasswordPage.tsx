import { useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { authApi } from '../services/api';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [done, setDone] = useState(false);

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg('');
    if (password.length < 8) { setMsg('密码至少需要8位'); return; }
    if (password !== confirm) { setMsg('两次输入的密码不一致'); return; }
    if (!token) { setMsg('缺少重置令牌，请从邮箱链接中获取'); return; }
    setLoading(true);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
      setMsg('密码重置成功，请使用新密码登录');
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || '重置失败，令牌可能已过期');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30">
      <div className="w-full max-w-sm bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-6">
        <h1 className="text-lg font-semibold text-foreground mb-1">重置密码</h1>
        <p className="text-xs text-muted-foreground mb-4">输入新的登录密码</p>

        {done ? (
          <div>
            <p className="text-sm text-secondary mb-4">{msg}</p>
            <Link to="/login" className="text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground inline-block">
              返回登录
            </Link>
          </div>
        ) : (
          <form onSubmit={handleReset} className="space-y-4">
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">新密码</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="至少8位字符" autoFocus
                className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            </div>
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">确认密码</label>
              <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
                placeholder="再次输入密码"
                className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            </div>
            {msg && <p className={`text-xs ${done ? 'text-secondary' : 'text-destructive'}`}>{msg}</p>}
            <button type="submit" disabled={loading}
              className="w-full text-sm py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {loading ? '重置中...' : '重置密码'}
            </button>
            <p className="text-xs text-muted-foreground text-center">
              <Link to="/login" className="hover:underline">返回登录</Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
