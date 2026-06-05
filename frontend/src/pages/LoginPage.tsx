// iCoDer Login — iCoDer Console 1:1 replica
import { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store';
import { authApi } from '../services/api';
import { useT } from '../i18n';

type Mode = 'login' | 'register' | 'forgot';

export default function LoginPage() {
  const t = useT();
  const { login } = useAuthStore();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const resetForm = () => { setError(''); setSuccess(''); setUsername(''); setPassword(''); setEmail(''); setFullName(''); };

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) { setError('请输入用户名和密码'); return; }
    setLoading(true); setError('');
    try {
      const res = await authApi.login(username, password);
      const { user, access_token, refresh_token, organizations, current_org_id } = res.data;
      login(user, access_token, refresh_token, organizations || [], current_org_id || '');
    } catch (err: any) {
      setError(err?.response?.data?.detail || '登录失败');
    } finally { setLoading(false); }
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim() || !email.trim() || !fullName.trim()) {
      setError('请填写所有字段'); return;
    }
    if (password.length < 8) { setError('密码至少需要8位'); return; }
    setLoading(true); setError('');
    try {
      const res = await authApi.register(username, password, email, fullName);
      const { user, access_token, refresh_token, organizations, current_org_id } = res.data;
      login(user, access_token, refresh_token, organizations || [], current_org_id || '');
    } catch (err: any) {
      setError(err?.response?.data?.detail || '注册失败');
    } finally { setLoading(false); }
  };

  const handleForgot = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) { setError('请输入邮箱地址'); return; }
    setLoading(true); setError(''); setSuccess('');
    try {
      await authApi.forgotPassword(email);
      setSuccess('如果该邮箱已注册，重置链接已发送。');
      setEmail('');
    } catch { setSuccess('如果该邮箱已注册，重置链接已发送。'); }
    finally { setLoading(false); }
  };

  const switchMode = (m: Mode) => { resetForm(); setMode(m); };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <h1 className="text-2xl font-brand font-bold text-foreground tracking-tight">iCoDer Console</h1>
          <p className="text-sm text-muted-foreground mt-1">{t.appTagline}</p>
        </div>

        <div className="border border-border rounded-xl p-8 bg-card">
          {mode === 'login' && (
            <>
              <h2 className="text-xl font-semibold text-foreground text-center mb-2">登录</h2>
              <p className="text-sm text-muted-foreground text-center mb-6">欢迎回来，请登录您的账户</p>
              <form onSubmit={handleLogin} className="space-y-4">
                {error && <div className="bg-destructive/10 border border-destructive/20 rounded-lg px-4 py-3 text-sm text-destructive">{error}</div>}
                <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                  placeholder="用户名" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20" required autoFocus />
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="密码" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20" required />
                <button type="submit" disabled={loading}
                  className="w-full inline-flex items-center justify-center rounded-lg font-medium bg-primary text-primary-foreground hover:bg-primary/90 px-5 py-2 min-h-[2.75rem] disabled:opacity-50">
                  {loading ? '登录中...' : '登 录'}
                </button>
              </form>
              {/* OAuth login — Corti-style */}
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-[10px] text-muted-foreground text-center mb-3">或使用第三方账号登录</p>
                <div className="flex gap-2">
                  <button onClick={() => window.location.href = '/api/oauth/authorize?response_type=code&client_id=google&redirect_uri=' + encodeURIComponent(window.location.origin + '/login')}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-border text-xs hover:bg-accent transition-colors">
                    <svg width="16" height="16" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                    Google
                  </button>
                  <button onClick={() => window.location.href = '/api/oauth/authorize?response_type=code&client_id=github&redirect_uri=' + encodeURIComponent(window.location.origin + '/login')}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-border text-xs hover:bg-accent transition-colors">
                    <svg width="16" height="16" viewBox="0 0 24 24"><path fill="currentColor" d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
                    GitHub
                  </button>
                </div>
              </div>
              <div className="flex justify-between mt-4">
                <button onClick={() => switchMode('forgot')} className="text-xs text-muted-foreground hover:text-primary">忘记密码？</button>
                <button onClick={() => switchMode('register')} className="text-xs text-muted-foreground hover:text-primary">没有账号？注册</button>
              </div>

            </>
          )}

          {mode === 'register' && (
            <>
              <h2 className="text-xl font-semibold text-foreground text-center mb-2">注册</h2>
              <p className="text-sm text-muted-foreground text-center mb-6">创建您的iCoDer账号</p>
              <form onSubmit={handleRegister} className="space-y-4">
                {error && <div className="bg-destructive/10 border border-destructive/20 rounded-lg px-4 py-3 text-sm text-destructive">{error}</div>}
                <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                  placeholder="用户名" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20" required autoFocus />
                <input type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                  placeholder="姓名" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20" required />
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="邮箱" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20" required />
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="密码（至少8位）" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20" required />
                <button type="submit" disabled={loading}
                  className="w-full inline-flex items-center justify-center rounded-lg font-medium bg-primary text-primary-foreground hover:bg-primary/90 px-5 py-2 min-h-[2.75rem] disabled:opacity-50">
                  {loading ? '注册中...' : '注 册'}
                </button>
              </form>
              <p className="text-xs text-muted-foreground text-center mt-4">
                已有账号？<button onClick={() => switchMode('login')} className="text-primary hover:underline ml-1">登录</button>
              </p>
            </>
          )}

          {mode === 'forgot' && (
            <>
              <h2 className="text-xl font-semibold text-foreground text-center mb-2">忘记密码</h2>
              <p className="text-sm text-muted-foreground text-center mb-6">输入注册邮箱，我们将发送重置链接</p>
              <form onSubmit={handleForgot} className="space-y-4">
                {error && <div className="bg-destructive/10 border border-destructive/20 rounded-lg px-4 py-3 text-sm text-destructive">{error}</div>}
                {success && <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-700">{success}</div>}
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="注册邮箱" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20" required autoFocus />
                <button type="submit" disabled={loading}
                  className="w-full inline-flex items-center justify-center rounded-lg font-medium bg-primary text-primary-foreground hover:bg-primary/90 px-5 py-2 min-h-[2.75rem] disabled:opacity-50">
                  {loading ? '发送中...' : '发送重置链接'}
                </button>
              </form>
              <p className="text-xs text-muted-foreground text-center mt-4">
                <button onClick={() => switchMode('login')} className="text-primary hover:underline">返回登录</button>
              </p>
            </>
          )}
        </div>

        <p className="text-xs text-muted-foreground text-center mt-8">
          使用前请阅读 <button onClick={() => navigate('/support')} className="text-primary hover:underline">隐私政策</button> 和 <button onClick={() => navigate('/support')} className="text-primary hover:underline">服务条款</button>
        </p>
      </div>
    </div>
  );
}
