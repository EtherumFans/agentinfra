import { Building2, Loader2, RefreshCw, Save, ShieldCheck, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { platformAdminApi } from '../services/api';
import { useAuthStore } from '../store';

const ROLES = [
  ['admin', '平台管理员'],
  ['coder', '编码员'],
  ['dept_head', '科室负责人'],
  ['insurance', '医保人员'],
  ['qc', '质控人员'],
  ['clinician', '临床医生'],
  ['it', '信息科'],
  ['cdi_specialist', 'CDI 专员'],
  ['medical_records_admin', '病案管理员'],
] as const;

const USER_REASONS = [
  ['role_assignment', '角色授予'],
  ['role_revocation', '角色回收'],
  ['account_suspension', '账户停用'],
  ['account_reactivation', '账户恢复'],
  ['security_response', '安全响应'],
  ['employment_change', '岗位变化'],
] as const;

const ORG_REASONS = [
  ['plan_change', '套餐变更'],
  ['organization_suspension', '组织停用'],
  ['organization_reactivation', '组织恢复'],
  ['security_response', '安全响应'],
] as const;

function detail(error: any): string {
  const value = error?.response?.data?.detail;
  if (typeof value === 'string') return value;
  return value?.message || value?.code || error?.message || '操作失败';
}

export default function PlatformAccessPage() {
  const currentUser = useAuthStore(s => s.user);
  const [tab, setTab] = useState<'users' | 'organizations'>('users');
  const [users, setUsers] = useState<any[]>([]);
  const [organizations, setOrganizations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [userDrafts, setUserDrafts] = useState<Record<string, any>>({});
  const [orgDrafts, setOrgDrafts] = useState<Record<string, any>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [userResponse, orgResponse] = await Promise.all([
        platformAdminApi.users(),
        platformAdminApi.organizations(),
      ]);
      setUsers(userResponse.data?.users || []);
      setOrganizations(orgResponse.data?.organizations || []);
    } catch (err) {
      setError(detail(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const userDraft = (user: any) => userDrafts[user.id] || {
    role: user.role,
    is_active: user.is_active,
    reason_code: 'role_assignment',
    ticket_id: '',
  };
  const orgDraft = (org: any) => orgDrafts[org.id] || {
    plan: org.plan,
    is_active: org.is_active,
    reason_code: 'plan_change',
    ticket_id: '',
  };

  const saveUser = async (user: any) => {
    const draft = userDraft(user);
    setSaving(`user:${user.id}`);
    setError('');
    setNotice('');
    try {
      const response = await platformAdminApi.updateUserAccess(user.id, {
        role: draft.role,
        is_active: draft.is_active,
        expected_token_version: user.token_version,
        reason_code: draft.reason_code,
        ...(draft.ticket_id ? { ticket_id: draft.ticket_id } : {}),
      });
      const updated = response.data.user;
      setUsers(items => items.map(item => item.id === updated.id ? updated : item));
      setUserDrafts(drafts => ({ ...drafts, [user.id]: { ...draft, role: updated.role, is_active: updated.is_active } }));
      setNotice(response.data.changed ? `已更新 ${updated.username}，旧凭证已撤销。` : '未检测到访问权限变化。');
    } catch (err) {
      setError(detail(err));
    } finally {
      setSaving('');
    }
  };

  const saveOrganization = async (org: any) => {
    const draft = orgDraft(org);
    setSaving(`org:${org.id}`);
    setError('');
    setNotice('');
    try {
      const response = await platformAdminApi.updateOrganization(org.id, {
        plan: draft.plan,
        is_active: draft.is_active,
        reason_code: draft.reason_code,
        ...(draft.ticket_id ? { ticket_id: draft.ticket_id } : {}),
      });
      setOrganizations(items => items.map(item => item.id === org.id ? { ...item, ...response.data } : item));
      setNotice(response.data.changed ? `已更新组织 ${org.name}。` : '未检测到组织设置变化。');
    } catch (err) {
      setError(detail(err));
    } finally {
      setSaving('');
    }
  };

  if (loading) return <div className="h-64 flex items-center justify-center"><Loader2 className="animate-spin" /></div>;

  return (
    <div className="min-h-dvh bg-muted/20 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-2"><ShieldCheck size={22} /><h1 className="text-2xl font-bold">平台访问控制</h1></div>
            <p className="text-sm text-muted-foreground mt-2">平台角色与组织角色相互独立。所有变更均撤销旧凭证并写入系统审计。</p>
          </div>
          <button onClick={load} className="border border-border rounded-lg px-3 py-2 text-sm flex items-center gap-2 hover:bg-accent"><RefreshCw size={14} />刷新</button>
        </div>

        {error && <div className="mb-4 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
        {notice && <div className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-700">{notice}</div>}

        <div className="flex gap-2 mb-4">
          <button onClick={() => setTab('users')} className={`px-4 py-2 rounded-lg text-sm flex items-center gap-2 ${tab === 'users' ? 'bg-primary text-primary-foreground' : 'bg-background border border-border'}`}><Users size={14} />用户</button>
          <button onClick={() => setTab('organizations')} className={`px-4 py-2 rounded-lg text-sm flex items-center gap-2 ${tab === 'organizations' ? 'bg-primary text-primary-foreground' : 'bg-background border border-border'}`}><Building2 size={14} />组织</button>
        </div>

        {tab === 'users' && <div className="space-y-3">
          {users.map(user => {
            const draft = userDraft(user);
            const self = user.id === currentUser?.id;
            return <div key={user.id} className="bg-background border border-border rounded-xl p-4 grid gap-3 lg:grid-cols-[1.4fr_1fr_0.8fr_1fr_1fr_auto] items-center">
              <div><p className="font-medium text-sm">{user.full_name || user.username}{self && <span className="ml-2 text-xs text-primary">当前账户</span>}</p><p className="text-xs text-muted-foreground">{user.email} · v{user.token_version}</p></div>
              <select disabled={self} value={draft.role} onChange={e => setUserDrafts(d => ({ ...d, [user.id]: { ...draft, role: e.target.value } }))} className="border border-border rounded-lg px-2 py-2 text-sm bg-background">{ROLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
              <label className="text-sm flex items-center gap-2"><input disabled={self} type="checkbox" checked={draft.is_active} onChange={e => setUserDrafts(d => ({ ...d, [user.id]: { ...draft, is_active: e.target.checked } }))} />启用</label>
              <select disabled={self} value={draft.reason_code} onChange={e => setUserDrafts(d => ({ ...d, [user.id]: { ...draft, reason_code: e.target.value } }))} className="border border-border rounded-lg px-2 py-2 text-sm bg-background">{USER_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
              <input disabled={self} value={draft.ticket_id} onChange={e => setUserDrafts(d => ({ ...d, [user.id]: { ...draft, ticket_id: e.target.value } }))} placeholder="工单号（可选）" className="border border-border rounded-lg px-2 py-2 text-sm bg-background" />
              <button disabled={self || saving === `user:${user.id}`} onClick={() => saveUser(user)} className="bg-primary text-primary-foreground rounded-lg px-3 py-2 text-sm flex items-center gap-1 disabled:opacity-40"><Save size={13} />保存</button>
            </div>;
          })}
        </div>}

        {tab === 'organizations' && <div className="space-y-3">
          {organizations.map(org => {
            const draft = orgDraft(org);
            return <div key={org.id} className="bg-background border border-border rounded-xl p-4 grid gap-3 lg:grid-cols-[1.4fr_0.7fr_0.7fr_1fr_1fr_auto] items-center">
              <div><p className="font-medium text-sm">{org.name}</p><p className="text-xs text-muted-foreground">{org.slug}</p></div>
              <select value={draft.plan} onChange={e => setOrgDrafts(d => ({ ...d, [org.id]: { ...draft, plan: e.target.value } }))} className="border border-border rounded-lg px-2 py-2 text-sm bg-background"><option value="free">Free</option><option value="pro">Pro</option><option value="enterprise">Enterprise</option></select>
              <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={draft.is_active} onChange={e => setOrgDrafts(d => ({ ...d, [org.id]: { ...draft, is_active: e.target.checked } }))} />启用</label>
              <select value={draft.reason_code} onChange={e => setOrgDrafts(d => ({ ...d, [org.id]: { ...draft, reason_code: e.target.value } }))} className="border border-border rounded-lg px-2 py-2 text-sm bg-background">{ORG_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
              <input value={draft.ticket_id} onChange={e => setOrgDrafts(d => ({ ...d, [org.id]: { ...draft, ticket_id: e.target.value } }))} placeholder="工单号（可选）" className="border border-border rounded-lg px-2 py-2 text-sm bg-background" />
              <button disabled={saving === `org:${org.id}`} onClick={() => saveOrganization(org)} className="bg-primary text-primary-foreground rounded-lg px-3 py-2 text-sm flex items-center gap-1 disabled:opacity-40"><Save size={13} />保存</button>
            </div>;
          })}
        </div>}
      </div>
    </div>
  );
}
