// iCoDer API Clients — API Keys + OAuth 2.0 Client management
import { Key, Plus, Trash2, Clock, Loader2, Copy, Check, Shield } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import { keysApi, oauthApi } from '../services/api';

type Tab = 'api-keys' | 'oauth-clients';

export default function APIClientsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('oauth-clients');
  const [keys, setKeys] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newScopes, setNewScopes] = useState('api:read api:write');
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [newClientId, setNewClientId] = useState<string | null>(null);
  const [copied, setCopied] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<{clientId: string; name: string} | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [kRes, cRes] = await Promise.allSettled([keysApi.list(), oauthApi.list()]);
      if (kRes.status === 'fulfilled') setKeys(kRes.value.data.keys || []);
      if (cRes.status === 'fulfilled') setClients(cRes.value.data.clients || []);
    } catch (err: any) { setError(err?.message || '加载失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleCreateOAuth = async () => {
    if (!newName.trim()) return;
    try {
      const res = await oauthApi.create(newName.trim(), newDesc.trim(), newScopes);
      setNewClientId(res.data.client_id);
      setNewSecret(res.data.client_secret);
      setShowNew(false); setNewName(''); setNewDesc('');
      fetchAll();
    } catch (err: any) { setError(err?.response?.data?.detail || '创建失败'); }
  };

  const handleDeleteOAuth = (clientId: string, name: string) => {
    setConfirmDelete({ clientId, name });
  };

  const handleCopy = (text: string, key: string) => { navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(''), 2000); };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin h-8 w-8 text-muted-foreground" /></div>;

  return (
    <div className="bg-muted/20 min-h-screen p-6">
      {error && (
        <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-destructive/60 hover:text-destructive">&times;</button>
        </div>
      )}

      {/* OAuth Secret reveal */}
      {newSecret && (
        <div className="mb-6 p-5 border-2 border-warning/30 bg-warning/10 rounded-xl shadow-sm ring-1 ring-warning/20 max-w-lg">
          <h3 className="text-sm font-semibold text-warning-foreground mb-2">OAuth客户端已创建</h3>
          <p className="text-xs text-warning-foreground/70 mb-3">复制Client Secret — 它不会再次显示。</p>
          <div className="space-y-2">
            <div className="flex items-center justify-between bg-background rounded p-2 border border-warning/20">
              <code className="text-xs font-mono">Client ID: {newClientId}</code>
              <button onClick={() => handleCopy(newClientId!, 'cid')} className="p-1">{copied === 'cid' ? <Check size={12} className="text-success" /> : <Copy size={12} />}</button>
            </div>
            <div className="flex items-center justify-between bg-background rounded p-2 border border-warning/20">
              <code className="text-xs font-mono break-all">{newSecret}</code>
              <button onClick={() => handleCopy(newSecret!, 'secret')} className="p-1">{copied === 'secret' ? <Check size={12} className="text-success" /> : <Copy size={12} />}</button>
            </div>
          </div>
          <button onClick={() => { setNewSecret(null); setNewClientId(null); }} className="text-xs text-warning-foreground/70 hover:underline mt-3">完成</button>
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-2">API 客户端</h2>
          <p className="text-sm text-muted-foreground">管理 API 密钥和 OAuth 2.0 客户端凭证</p>
        </div>
        <button onClick={() => setShowNew(!showNew)} className="bg-primary text-primary-foreground rounded-lg flex items-center gap-2 px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">
          <Plus size={16} /> 创建OAuth客户端
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex items-center rounded-lg border border-border/20 p-0.5 bg-background">
          <button onClick={() => setActiveTab('oauth-clients')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${activeTab === 'oauth-clients' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
            <Shield size={14} className="inline mr-1.5" /> OAuth 2.0 客户端
          </button>
          <button onClick={() => setActiveTab('api-keys')}
            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${activeTab === 'api-keys' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
            <Key size={14} className="inline mr-1.5" /> API 密钥
          </button>
        </div>
      </div>

      {/* Create form */}
      {showNew && (
        <div className="border border-border/20 rounded-xl shadow-sm ring-1 ring-border/20 p-5 mb-6 max-w-lg bg-background">
          <h3 className="text-sm font-semibold text-foreground mb-3">创建 OAuth 2.0 客户端 (Client Credentials)</h3>
          <div className="space-y-3">
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="客户端名称（如：生产环境SDK）" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" onKeyDown={e => e.key === 'Enter' && handleCreateOAuth()} />
            <input value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="描述（可选）" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
            <input value={newScopes} onChange={e => setNewScopes(e.target.value)} placeholder="Scopes（空格分隔）" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring font-mono text-xs" />
            <div className="flex gap-2">
              <button onClick={handleCreateOAuth} className="bg-primary text-primary-foreground rounded-lg text-sm px-4 py-2 font-medium hover:bg-primary/90 transition-colors disabled:opacity-50" disabled={!newName.trim()}>创建</button>
              <button onClick={() => { setShowNew(false); setNewName(''); }} className="px-4 py-2 text-sm rounded-lg border border-border/20 hover:bg-accent transition-colors text-muted-foreground">取消</button>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-2xl">
        {activeTab === 'oauth-clients' ? (
          clients.length === 0 ? (
            <div className="text-center py-12 border border-border/20 rounded-xl shadow-sm ring-1 ring-border/20 bg-background">
              <Shield size={48} className="mx-auto mb-3 text-muted-foreground/20" />
              <p className="text-sm text-muted-foreground">暂无OAuth客户端</p>
              <p className="text-xs text-muted-foreground mt-1">创建客户端以使用 client_credentials 认证</p>
            </div>
          ) : (
            clients.map((c: any) => (
              <div key={c.client_id} className="border border-border/20 rounded-xl shadow-sm ring-1 ring-border/20 p-4 mb-3 bg-background hover:bg-accent/50 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center"><Shield size={14} className="text-primary" /></div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{c.name}</p>
                      <p className="text-xs font-mono text-muted-foreground">{c.client_id}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="font-mono text-[10px] bg-muted px-1.5 py-0.5 rounded">{c.scopes}</span>
                    {c.last_used_at && <span className="flex items-center gap-1"><Clock size={12} /> {c.last_used_at?.split('T')[0]}</span>}
                    <button onClick={() => handleDeleteOAuth(c.client_id, c.name)} className="text-destructive hover:text-destructive/80"><Trash2 size={14} /></button>
                  </div>
                </div>
              </div>
            ))
          )
        ) : (
          keys.length === 0 ? (
            <div className="text-center py-12 border border-border/20 rounded-xl shadow-sm ring-1 ring-border/20 bg-background">
              <Key size={48} className="mx-auto mb-3 text-muted-foreground/20" />
              <p className="text-sm text-muted-foreground">暂无API密钥</p>
            </div>
          ) : (
            keys.map((k: any) => (
              <div key={k.id} className="border border-border/20 rounded-xl shadow-sm ring-1 ring-border/20 p-4 mb-3 bg-background hover:bg-accent/50 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center"><Key size={14} className="text-primary-foreground" /></div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{k.name}</p>
                      <p className="text-xs font-mono text-muted-foreground">{k.key_prefix}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><Clock size={12} /> {k.created_at?.split('T')[0]}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{k.status}</span>
                    <button onClick={() => keysApi.delete(k.id).then(() => setKeys(keys.filter(x => x.id !== k.id)))} className="text-destructive hover:text-destructive/80"><Trash2 size={14} /></button>
                  </div>
                </div>
              </div>
            ))
          )
        )}
      </div>

      {/* Confirm delete modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setConfirmDelete(null)}>
          <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 w-full max-w-sm p-6 mx-4" onClick={e => e.stopPropagation()}>
            <div className="w-1 h-4 rounded-full bg-primary/40 mb-3" />
            <h3 className="text-sm font-semibold text-foreground mb-2">确认撤销</h3>
            <p className="text-sm text-muted-foreground mb-4">
              撤销OAuth客户端 "{confirmDelete.name}"？使用此客户端的应用将无法认证。
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmDelete(null)} className="px-3 py-1.5 text-xs rounded-lg border border-border/20 hover:bg-accent transition-colors text-muted-foreground">取消</button>
              <button onClick={async () => {
                try {
                  await oauthApi.delete(confirmDelete.clientId);
                  setClients(clients.filter(c => c.client_id !== confirmDelete.clientId));
                } catch (err: any) {
                  setError(err?.response?.data?.detail || '删除失败');
                }
                setConfirmDelete(null);
              }} className="px-3 py-1.5 text-xs rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors">确认撤销</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
