import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { authApi, orgApi } from '../services/api';
import { useAuthStore } from '../store';

type ViewState = 'needs-auth' | 'accepting' | 'accepted' | 'error';

function readInviteToken(): string | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const token = params.get('token') || '';
  return /^[A-Za-z0-9_-]{32,256}$/.test(token) ? token : null;
}

export default function AcceptInvitePage() {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const setOrganizations = useAuthStore((state) => state.setOrganizations);
  const tokenRef = useRef<string | null>(readInviteToken());
  const startedRef = useRef(false);
  const [viewState, setViewState] = useState<ViewState>(
    isAuthenticated ? 'accepting' : 'needs-auth',
  );
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!isAuthenticated || startedRef.current) return;
    startedRef.current = true;
    const token = tokenRef.current;
    // Remove the bearer credential from browser history before the request.
    window.history.replaceState({}, document.title, '/accept-invite');
    if (!token) {
      setMessage('邀请链接无效或缺少凭证。');
      setViewState('error');
      return;
    }

    void (async () => {
      try {
        const accepted = await orgApi.acceptInvite(token);
        tokenRef.current = null;
        const orgId = accepted.data.id as string;
        const switched = await authApi.switchOrg(orgId);
        localStorage.setItem('access_token', switched.data.access_token);
        localStorage.setItem('refresh_token', switched.data.refresh_token);
        setOrganizations(switched.data.organizations || [], switched.data.current_org_id || orgId);
        setMessage(`已加入组织“${accepted.data.name}”。`);
        setViewState('accepted');
      } catch (error: any) {
        tokenRef.current = null;
        const detail = error?.response?.data?.detail;
        setMessage(typeof detail === 'string' ? detail : '邀请无法接受，请联系组织管理员。');
        setViewState('error');
      }
    })();
  }, [isAuthenticated, setOrganizations]);

  const goToLogin = () => {
    // Keep the credential in the URL fragment so it is not sent to the server.
    const token = tokenRef.current;
    navigate(token ? `/login#token=${encodeURIComponent(token)}` : '/login');
  };

  return (
    <div className="min-h-dvh flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 text-center">
        <h1 className="text-xl font-semibold text-foreground">组织邀请</h1>
        {viewState === 'needs-auth' && (
          <>
            <p className="mt-3 text-sm text-muted-foreground">请先登录或注册邀请邮箱对应的账号。</p>
            <button className="mt-6 rounded-lg bg-primary px-5 py-2 text-primary-foreground" onClick={goToLogin}>
              继续登录
            </button>
          </>
        )}
        {viewState === 'accepting' && <p className="mt-4 text-sm text-muted-foreground">正在验证并接受邀请…</p>}
        {viewState === 'accepted' && (
          <>
            <p className="mt-4 text-sm text-foreground">{message}</p>
            <button className="mt-6 rounded-lg bg-primary px-5 py-2 text-primary-foreground" onClick={() => navigate('/', { replace: true })}>
              进入控制台
            </button>
          </>
        )}
        {viewState === 'error' && (
          <>
            <p className="mt-4 text-sm text-destructive">{message}</p>
            <button className="mt-6 rounded-lg border border-border px-5 py-2 text-foreground" onClick={() => navigate('/', { replace: true })}>
              返回控制台
            </button>
          </>
        )}
      </div>
    </div>
  );
}
