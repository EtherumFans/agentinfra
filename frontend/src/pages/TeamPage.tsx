// iCoDer Team Page - connected to real backend
import { Users, UserPlus, Shield, Trash2, Loader2, Mail, Clock } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';

import { useT } from '../i18n';
import { teamApi } from '../services/api';

const ROLE_LABELS: Record<string, string> = {
  owner: '拥有者',
  admin: '管理员',
  coder: '编码员',
  dept_head: '科室主任',
  viewer: '查看者',
};

export default function TeamPage() {
  const t = useT();
  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('coder');
  const [invitations, setInvitations] = useState<any[]>([]);
  const [activeSection, setActiveSection] = useState<'members' | 'invitations'>('members');
  const [removeConfirm, setRemoveConfirm] = useState<{id: string; name: string} | null>(null);

  const fetchMembers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await teamApi.members();
      setMembers(res.data.members || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '加载团队成员失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchMembers(); }, [fetchMembers]);
  useEffect(() => { teamApi.invitations().then(r => setInvitations(r.data?.invitations || [])).catch(() => {}); }, []);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    try {
      await teamApi.invite(inviteEmail.trim(), inviteRole);
      setShowInvite(false);
      setInviteEmail('');
      fetchMembers();
    } catch (err: any) {
      if (err?.response?.status === 409) {
        setError('该成员已在团队中。');
      } else {
        setError(err?.response?.data?.detail || err.message || '邀请失败');
      }
    }
  };

  const handleRemove = async (id: string, name: string) => {
    setRemoveConfirm({ id, name });
  };
  const confirmRemove = async () => {
    if (!removeConfirm) return;
    try {
      await teamApi.remove(removeConfirm.id);
      setMembers(members.filter(m => m.id !== removeConfirm.id));
      setRemoveConfirm(null);
    } catch (err: any) {
      setRemoveConfirm(null);
      setError(err?.response?.data?.detail || err.message || '移除失败');
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
    </div>
  );

  return (
    <div className="bg-muted/20 min-h-dvh p-6">
      {error && (
        <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-destructive/60 hover:text-destructive">&times;</button>
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-2">{t.teamTitle}</h2>
          <p className="text-sm text-muted-foreground">{t.teamDesc}</p>
        </div>
        <button onClick={() => setShowInvite(!showInvite)} className="bg-primary text-primary-foreground rounded-lg flex items-center gap-2 px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">
          <UserPlus size={16} /> {t.inviteMember}
        </button>
      </div>

      {showInvite && (
        <div className="border border-border/20 rounded-xl shadow-sm p-5 mb-6 max-w-lg bg-background">
          <h3 className="text-sm font-semibold text-foreground mb-3">邀请团队成员</h3>
          <div className="space-y-3">
            <input
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="邮箱地址"
              className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
              type="email"
              onKeyDown={(e) => e.key === 'Enter' && handleInvite()}
            />
            <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring">
              <option value="coder">编码员</option>
              <option value="dept_head">科室主任</option>
              <option value="viewer">查看者</option>
            </select>
            <div className="flex gap-2">
              <button onClick={handleInvite} className="bg-primary text-primary-foreground rounded-lg text-sm px-4 py-2 font-medium hover:bg-primary/90 transition-colors disabled:opacity-50" disabled={!inviteEmail.trim()}>发送邀请</button>
              <button onClick={() => { setShowInvite(false); setInviteEmail(''); }} className="px-4 py-2 text-sm rounded-lg border border-border/20 hover:bg-accent transition-colors text-muted-foreground">{t.cancel}</button>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-2xl">
        {/* Tab switcher - iCoDer-style */}
        <div className="flex items-center gap-1 mb-4" role="tablist">
          <button role="tab" aria-selected={activeSection === 'members'} onClick={() => setActiveSection('members')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${activeSection === 'members' ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>团队成员</button>
          <button role="tab" aria-selected={activeSection === 'invitations'} onClick={() => setActiveSection('invitations')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-1.5 ${activeSection === 'invitations' ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
            邀请
            {invitations.length > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-warning/10 text-warning-foreground">{invitations.length}</span>}
          </button>
        </div>

        {/* Members list */}
        {activeSection === 'members' && (
          members.length === 0 ? (
            <div className="text-center py-12 border border-border/20 rounded-xl shadow-sm bg-background">
              <Users size={48} className="mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">暂无团队成员</p>
            </div>
          ) : (
            members.map((member: any) => (
              <div key={member.id} className="flex items-center gap-4 p-4 border-b border-border/20 hover:bg-accent/50 transition-colors">
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-[10px] font-medium text-primary-foreground shrink-0">
                  {member.avatar || member.name?.split(' ').map((n: string) => n[0]).join('').toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">{member.name}</p>
                  <p className="text-xs text-muted-foreground">{member.email}</p>
                </div>
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Shield size={12} /> {ROLE_LABELS[member.role] || member.role}
                </span>
                <button
                  onClick={() => handleRemove(member.id, member.name)}
                  className="text-destructive/60 hover:text-destructive ml-2"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )
        )}

        {/* Invitations list */}
        {activeSection === 'invitations' && (
          invitations.length === 0 ? (
            <div className="text-center py-12 border border-border/20 rounded-xl shadow-sm bg-background">
              <Mail size={48} className="mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">暂无待处理的邀请</p>
            </div>
          ) : (
            invitations.map((inv: any) => (
              <div key={inv.id} className="flex items-center gap-4 p-4 border-b border-border/20">
                <div className="w-8 h-8 rounded-full bg-warning/10 flex items-center justify-center shrink-0">
                  <Mail size={14} className="text-warning-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">{inv.email}</p>
                  <p className="text-xs text-muted-foreground flex items-center gap-2">
                    <span>{ROLE_LABELS[inv.role] || inv.role}</span>
                    <span className="w-1 h-1 rounded-full bg-muted-foreground/40" />
                    <span className="flex items-center gap-1"><Clock size={10} /> {inv.invited_at ? new Date(inv.invited_at).toLocaleDateString() : ''}</span>
                  </p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-warning/10 text-warning-foreground font-medium">待处理</span>
              </div>
            ))
          )
        )}
      </div>

      {removeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setRemoveConfirm(null)}>
          <div className="bg-card rounded-xl border border-border shadow-xl w-full max-w-sm mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-5">
              <p className="text-sm font-medium text-foreground">确定将 {removeConfirm.name} 移出团队？</p>
              <p className="text-xs text-muted-foreground mt-1">此操作不可撤销。</p>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-muted/20">
              <button onClick={() => setRemoveConfirm(null)} className="text-xs px-4 py-2 rounded-lg hover:bg-accent transition-colors">取消</button>
              <button onClick={confirmRemove} className="text-xs px-4 py-2 rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors">确认</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
