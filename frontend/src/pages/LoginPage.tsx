// iCoDer Login - iCoDer Console 1:1 replica
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
    <div className="min-h-dvh flex flex-col items-center justify-center bg-background">
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
                  placeholder="用户名" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20" required autoFocus />
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="密码" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20" required />
                <button type="submit" disabled={loading}
                  className="w-full inline-flex items-center justify-center rounded-lg font-medium bg-primary text-primary-foreground hover:bg-primary/90 px-5 py-2 min-h-[2.75rem] disabled:opacity-50">
                  {loading ? '登录中...' : '登 录'}
                </button>
              </form>
              {/* OAuth login */}
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-[10px] text-muted-foreground text-center mb-3">或使用第三方账号登录</p>
                <div className="flex gap-2">
                  <button onClick={() => window.location.href = '/api/oauth/authorize?response_type=code&client_id=google&redirect_uri=' + encodeURIComponent(window.location.origin + '/login')}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-border text-xs hover:bg-accent transition-colors">
                    <img src="https://cdn.simpleicons.org/google/4285F4" alt="Google" width="16" height="16" loading="lazy" />
                    Google
                  </button>
                  <button onClick={() => window.location.href = '/api/oauth/authorize?response_type=code&client_id=github&redirect_uri=' + encodeURIComponent(window.location.origin + '/login')}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-border text-xs hover:bg-accent transition-colors">
                    <img src="https://cdn.simpleicons.org/github/181717" alt="GitHub" width="16" height="16" loading="lazy" className="dark:hidden" />
                    <img src="https://cdn.simpleicons.org/github/ffffff" alt="GitHub" width="16" height="16" loading="lazy" className="hidden dark:block" />
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
                  placeholder="用户名" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20" required autoFocus />
                <input type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                  placeholder="姓名" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20" required />
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="邮箱" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20" required />
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="密码（至少8位）" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20" required />
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
                  placeholder="注册邮箱" className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/20" required autoFocus />
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
