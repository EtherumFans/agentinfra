// iCoDer - Settings Page with real config
import { useState, useEffect } from 'react';
import { useAuthStore } from '../store';
import type { OrgInfo } from '../store';
import { Settings, User, Shield, Database, Activity, Loader2, ExternalLink as ExternalLinkIcon, Check, Building2, UserPlus, X, ChevronDown, Lock, Key } from 'lucide-react';
import { useT } from '../i18n';
import { configApi, a2aApi, orgApi, authApi } from '../services/api';

const COUNTRIES = [
  { value: 'US', label: 'United States' },
  { value: 'CN', label: '中国' },
  { value: 'JP', label: '日本' },
  { value: 'GB', label: 'United Kingdom' },
  { value: 'DE', label: 'Germany' },
  { value: 'FR', label: 'France' },
  { value: 'CA', label: 'Canada' },
  { value: 'AU', label: 'Australia' },
  { value: 'KR', label: 'South Korea' },
  { value: 'BR', label: 'Brazil' },
  { value: 'IN', label: 'India' },
  { value: 'IT', label: 'Italy' },
  { value: 'ES', label: 'Spain' },
  { value: 'MX', label: 'Mexico' },
  { value: 'NL', label: 'Netherlands' },
  { value: 'CH', label: 'Switzerland' },
  { value: 'SE', label: 'Sweden' },
  { value: 'SG', label: 'Singapore' },
  { value: 'AE', label: 'United Arab Emirates' },
  { value: 'SA', label: 'Saudi Arabia' },
  { value: 'OTHER', label: 'Other' },
];

export default function SettingsPage() {
  const t = useT();
  const { user } = useAuthStore();
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [a2aAgents, setA2aAgents] = useState<any[]>([]);
  const [country, setCountry] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordMsg, setPasswordMsg] = useState('');
  const [guards, setGuards] = useState([
    { key: 'no_medication_prescription', name: '处方拦截', desc: '阻止AI输出药物处方建议', severity: 'error', enabled: true },
    { key: 'no_diagnosis_without_disclaimer', name: '诊断免责声明', desc: '编码建议非临床诊断，自动添加免责声明', severity: 'warning', enabled: true },
    { key: 'no_emergency_triage', name: '急诊分诊拦截', desc: '防止AI执行急诊分诊建议', severity: 'error', enabled: true },
    { key: 'suspicious_code_format', name: '可疑编码格式', desc: '检测异常精确的编码（可能是幻觉）', severity: 'warning', enabled: true },
    { key: 'phi_detected', name: 'PHI检测', desc: '扫描输入中的个人隐私信息（身份证/手机号/邮箱等）', severity: 'warning', enabled: true },
    { key: 'blocked_term', name: '屏蔽词检测', desc: '检测安全攻击关键词（inject/bypass等）', severity: 'error', enabled: true },
  ]);

  // Organization management state
  const { organizations, currentOrgId } = useAuthStore();
  const currentOrg = organizations.find((o: OrgInfo) => o.id === currentOrgId);
  const [orgMembers, setOrgMembers] = useState<any[]>([]);
  const [orgMembersLoading, setOrgMembersLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState('');

  const isOrgAdmin = currentOrg?.role === 'owner' || currentOrg?.role === 'admin';

  const fetchOrgMembers = async () => {
    if (!currentOrgId) return;
    setOrgMembersLoading(true);
    try {
      const { data } = await orgApi.getMembers(currentOrgId);
      setOrgMembers(data);
    } catch { setOrgMembers([]); }
    finally { setOrgMembersLoading(false); }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim() || !currentOrgId) return;
    setInviting(true); setInviteMsg('');
    try {
      const { data } = await orgApi.invite(currentOrgId, { email: inviteEmail, role: inviteRole });
      setInviteMsg(data.message || '邀请已发送');
      setInviteEmail('');
      fetchOrgMembers();
    } catch (err: any) {
      setInviteMsg(err?.response?.data?.detail || '邀请失败');
    } finally { setInviting(false); }
  };

  const handleRemoveMember = async (userId: string) => {
    if (!currentOrgId || !confirm('确认移除此成员？')) return;
    try {
      await orgApi.removeMember(currentOrgId, userId);
      fetchOrgMembers();
    } catch {}
  };

  const handleRoleChange = async (userId: string, newRole: string) => {
    if (!currentOrgId) return;
    try {
      await orgApi.updateMemberRole(currentOrgId, userId, { role: newRole });
      fetchOrgMembers();
    } catch {}
  };

  useEffect(() => { fetchOrgMembers(); }, [currentOrgId]);

  // Existing state
  const [saving, setSaving] = useState(false);
  const [showSavedToast, setShowSavedToast] = useState(false);

  useEffect(() => {
    configApi.get()
      .then(res => setConfig(res.data))
      .catch(() => setConfig(null))
      .finally(() => setLoading(false));
  }, []);

  const fetchA2a = () => {
    a2aApi.discoverAgents().then(res => setA2aAgents(res.data.agents || [])).catch(() => {});
  };
  useEffect(() => { fetchA2a(); }, []);


  const toggleGuard = (key: string) => {
    setGuards(prev => prev.map(g => g.key === key ? {...g, enabled: !g.enabled} : g));
  };

  const handleChangePassword = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordMsg('请填写所有密码字段'); return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMsg('两次输入的新密码不一致'); return;
    }
    if (newPassword.length < 8) {
      setPasswordMsg('新密码至少需要8位'); return;
    }
    setChangingPassword(true); setPasswordMsg('');
    try {
      const token = localStorage.getItem('access_token') || '';
      const r = await fetch('/api/auth/change-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (r.ok) {
        setPasswordMsg('密码修改成功'); setCurrentPassword(''); setNewPassword(''); setConfirmPassword('');
      } else {
        const d = await r.json(); setPasswordMsg(d.detail || '修改失败');
      }
    } catch { setPasswordMsg('网络错误'); }
    setChangingPassword(false);
  };

  const handleRevokeSessions = async () => {
    if (!confirm('确定要登出所有设备吗？所有会话将立即失效。')) return;
    try {
      await authApi.revokeTokens('manual');
      alert('所有会话已失效。请重新登录。');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    } catch { alert('操作失败'); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      localStorage.setItem('icoder-settings', JSON.stringify({ country, guards }));
      await new Promise(r => setTimeout(r, 300));
      setSaving(false);
      setShowSavedToast(true);
      setTimeout(() => setShowSavedToast(false), 3000);
    } catch {
      setSaving(false);
    }
  };

  // Load saved settings on mount
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('icoder-settings') || '{}');
      if (saved.country) setCountry(saved.country);
      if (saved.guards) setGuards(saved.guards);
    } catch {}
  }, []);

  return (
    <div className="bg-muted/20 min-h-screen p-6">
      <h2 className="text-2xl font-bold text-foreground mb-6">{t.settingsTitle}</h2>

      <div className="grid grid-cols-2 gap-6">
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <User size={18} /> {t.account}
          </h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">{t.username}</label>
              <p className="font-medium text-foreground">{user?.username}</p>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.fullName}</label>
              <p className="font-medium text-foreground">{user?.full_name}</p>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.role}</label>
              <p className="font-medium text-foreground">{user?.role}</p>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.department}</label>
              <p className="font-medium text-foreground">{user?.department}</p>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">国家/地区</label>
              <select value={country} onChange={e => setCountry(e.target.value)}
                className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring mt-0.5 text-xs">
                <option value="">-- 选择国家/地区 --</option>
                {COUNTRIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
          </div>
        </div>

        {/* Change Password */}
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Lock size={18} /> 修改密码
          </h3>
          <div className="space-y-3">
            <input type="password" placeholder="当前密码" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}
              className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            <input type="password" placeholder="新密码（至少8位）" value={newPassword} onChange={e => setNewPassword(e.target.value)}
              className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            <input type="password" placeholder="确认新密码" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
              className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            <button onClick={handleChangePassword} disabled={changingPassword}
              className="w-full py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {changingPassword ? '修改中...' : '修改密码'}
            </button>
            {passwordMsg && <p className={`text-xs ${passwordMsg.includes('成功') ? 'text-green-600' : 'text-red-500'}`}>{passwordMsg}</p>}
          </div>
          <button onClick={handleRevokeSessions}
            className="mt-3 w-full py-2 rounded-lg text-xs font-medium bg-red-50 text-red-600 hover:bg-red-100 border border-red-200">
            登出所有设备
          </button>
        </div>

        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Activity size={18} /> {t.systemInformation}
          </h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">{t.product}</label>
              <p className="font-medium text-foreground">{config?.app || 'iCoDer 医学编码智能体'} {config?.version || ''}</p>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.llmProvider}</label>
              <p className="font-medium text-foreground">{config?.llm_provider || 'DeepSeek'} / {config?.llm_model || 'deepseek-chat'}</p>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.environment}</label>
              <p className="font-medium text-foreground">{config?.environment || '开发环境'}</p>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">状态</label>
              <p className="font-medium text-foreground flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${config?.status === 'healthy' ? 'bg-success' : 'bg-destructive'}`} />
                {config?.status === 'healthy' ? '运行正常' : '未知'}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Shield size={18} /> 安全护栏
          </h3>
          <div className="space-y-3">
            {guards.map(rule => (
              <div key={rule.key} className="flex items-center justify-between py-1.5 border-b border-border/20 last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full ${rule.severity === 'error' ? 'bg-destructive' : 'bg-warning'}`} />
                    <span className="text-sm font-medium text-foreground">{rule.name}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${rule.severity === 'error' ? 'bg-destructive/10 text-destructive' : 'bg-warning/10 text-warning-foreground'}`}>{rule.severity === 'error' ? '错误' : '警告'}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{rule.desc}</p>
                </div>
                <button onClick={() => toggleGuard(rule.key)}
                  className={`relative w-8 h-5 rounded-full transition-colors shrink-0 ml-3 ${rule.enabled ? 'bg-primary' : 'bg-muted border border-border/20'}`}>
                  <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-all ${rule.enabled ? 'left-3.5' : 'left-0.5'}`} />
                </button>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-4 pt-3 border-t border-border/20">
            护栏规则在每次智能体请求前后执行。错误级别违规会阻止请求，警告级别会添加提示。
          </p>
        </div>

        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <ExternalLinkIcon size={18} /> A2A 智能体
          </h3>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {a2aAgents.length === 0 ? (
              <p className="text-xs text-muted-foreground">加载中...</p>
            ) : (
              a2aAgents.map((a: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs py-1 border-b border-border/20 last:border-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-success" />
                  <span className="font-medium text-foreground">{a.name}</span>
                  <span className="text-muted-foreground">v{a.version}</span>
                  <div className="flex-1" />
                  <span className="text-[10px] text-muted-foreground">
                    {a.capabilities?.slice(0, 2).join(', ')}
                  </span>
                </div>
              ))
            )}
          </div>
          <button onClick={fetchA2a} className="text-xs text-primary hover:underline mt-2">刷新智能体列表</button>
        </div>

        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Database size={18} /> {t.codingSystems || '编码系统'}
          </h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">默认编码系统</label>
              <select defaultValue="ICD10_CN_2025" className="w-full text-xs border border-border rounded-lg px-2.5 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring mt-1">
                <option value="ICD10_CN_2025">ICD-10-CN 国标版 (2025)</option>
                <option value="ICD10_CN_MI_2025">ICD-10-CN 医保版 (2025)</option>
                <option value="ICD9_CM3_2025">ICD-9-CM-3 国标版 (2025)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">置信度阈值</label>
              <div className="flex items-center gap-2 mt-1">
                <input type="range" min="0" max="100" defaultValue="60" className="flex-1" />
                <span className="text-xs font-mono w-8 text-right">0.60</span>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Activity size={18} /> API 限流
          </h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">每分钟请求限制</label>
              <p className="text-lg font-bold font-mono">100 <span className="text-xs text-muted-foreground font-normal">req/min</span></p>
              <div className="h-2 bg-muted rounded-full mt-1.5 overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: '12%' }} />
              </div>
              <p className="text-[10px] text-muted-foreground mt-1">当前使用: ~12 req/min (12%)</p>
            </div>
            <div className="pt-2 border-t border-border/20">
              <p className="text-xs text-muted-foreground">速率限制基于滑动窗口算法 · 超限返回 HTTP 429 · 健康检查和静态文件不计数</p>
            </div>
          </div>
        </div>

        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Database size={18} /> 通知偏好
          </h3>
          <div className="space-y-3">
            {[
              { k: 'email_daily', label: '每日编码审核摘要', desc: '每天早上发送前一天的编码审核统计报告' },
              { k: 'email_alert', label: '编码异常告警', desc: '当出现编码冲突、信心度低或DRG风险时发送邮件告警' },
              { k: 'browser_notify', label: '浏览器通知', desc: '审核完成后在浏览器中弹出完成通知' },
            ].map(n => (
              <div key={n.k} className="flex items-center justify-between py-1.5 border-b border-border/20 last:border-0">
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-foreground">{n.label}</span>
                  <p className="text-xs text-muted-foreground">{n.desc}</p>
                </div>
                <button className={`relative w-8 h-5 rounded-full transition-colors shrink-0 ml-3 bg-muted border border-border/20`}>
                  <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-all left-0.5" />
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
          <h3 className="font-semibold text-foreground mb-4 flex items-center gap-2">
            <Database size={18} /> 数据与合规
          </h3>
          <p className="text-sm text-muted-foreground">
            SQLite + SQLAlchemy async · ICD-10-CN + ICD-9-CM-3 · 审计日志365天保留 ·
            9步智能体管线+动态LLM规划器 · 护栏规则6条
          </p>
        </div>
      </div>

      {/* ===== Organization Management ===== */}
      {currentOrg && (
        <div className="mt-8">
          <h3 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
            <Building2 size={20} /> {t.orgManage || 'Organization Management'}
          </h3>
          <div className="grid grid-cols-1 gap-6">
            {/* Org Info */}
            <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
              <h4 className="font-medium text-foreground mb-3">{currentOrg.name}</h4>
              <div className="flex gap-4 text-sm text-muted-foreground">
                <span>Plan: <strong className="text-foreground capitalize">{currentOrg.plan}</strong></span>
                <span>Role: <strong className="text-foreground capitalize">{currentOrg.role}</strong></span>
                <span>Slug: <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{currentOrg.slug}</code></span>
              </div>
            </div>

            {/* Member List */}
            <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
              <h4 className="font-medium text-foreground mb-4">{t.orgMembers || 'Members'} ({orgMembers.length})</h4>
              {orgMembersLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 size={14} className="animate-spin" /> Loading...</div>
              ) : (
                <div className="space-y-1">
                  {orgMembers.map((m: any) => (
                    <div key={m.user_id} className="flex items-center justify-between py-2 border-b border-border/10 last:border-0">
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium text-foreground">{m.full_name || m.username || m.email}</span>
                        <span className="text-xs text-muted-foreground ml-2">{m.email}</span>
                      </div>
                      {isOrgAdmin && m.role !== 'owner' ? (
                        <div className="flex items-center gap-2">
                          <select
                            value={m.role}
                            onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                            className="text-xs bg-muted border border-border rounded px-2 py-1 text-foreground"
                          >
                            <option value="admin">Admin</option>
                            <option value="member">Member</option>
                            <option value="viewer">Viewer</option>
                          </select>
                          <button onClick={() => handleRemoveMember(m.user_id)}
                            className="p-1 text-muted-foreground hover:text-red-500 transition-colors">
                            <X size={14} />
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs capitalize px-2 py-0.5 rounded bg-muted text-muted-foreground">{m.role}</span>
                      )}
                    </div>
                  ))}
                  {orgMembers.length === 0 && (
                    <p className="text-sm text-muted-foreground py-2">No members found</p>
                  )}
                </div>
              )}
            </div>

            {/* Invite Form */}
            {isOrgAdmin && (
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
                <h4 className="font-medium text-foreground mb-3 flex items-center gap-2">
                  <UserPlus size={16} /> {t.orgInvite || 'Invite Member'}
                </h4>
                <div className="flex gap-2">
                  <input
                    type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder={t.orgInviteEmail || 'Email address'}
                    className="flex-1 min-h-[2.5rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20"
                  />
                  <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}
                    className="text-sm bg-card border border-input rounded-lg px-3 py-2 text-foreground">
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
                  </select>
                  <button onClick={handleInvite} disabled={inviting || !inviteEmail.trim()}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors">
                    {inviting ? <Loader2 size={14} className="animate-spin" /> : (t.orgInvite || 'Invite')}
                  </button>
                </div>
                {inviteMsg && (
                  <p className={`mt-2 text-xs ${inviteMsg.includes('失败') || inviteMsg.includes('error') ? 'text-red-500' : 'text-green-500'}`}>
                    {inviteMsg}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Save button + toast */}
      <div className="mt-8 flex items-center gap-4">
        <button onClick={handleSave} disabled={saving}
          className="bg-primary text-primary-foreground rounded-lg flex items-center gap-2 px-6 py-2.5 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-60">
          {saving ? (
            <><Loader2 size={16} className="animate-spin" /> 保存中...</>
          ) : (
            <><Check size={16} /> 保存设置</>
          )}
        </button>
        {showSavedToast && (
          <div className="flex items-center gap-2 text-sm text-success bg-success/10 border border-success/20 rounded-lg px-4 py-2 animate-in fade-in slide-in-from-top-1">
            <Check size={16} className="text-success" />
            <span>设置已保存</span>
          </div>
        )}
      </div>
    </div>
  );
}
