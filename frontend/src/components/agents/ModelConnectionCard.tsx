import { useEffect, useState } from 'react';
import api from '../../services/api';

type Connection = {configured: boolean; enabled: boolean; model: string; version: number; editable: boolean; external_allowed: boolean; encryption_ready: boolean};

export default function ModelConnectionCard({onChanged}: {onChanged: () => void}) {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [model, setModel] = useState('deepseek-v4-flash');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const load = async () => {
    const {data} = await api.get<Connection>('/v1/model-connection');
    setConnection(data); setModel(data.model);
  };
  useEffect(() => {void load().catch(() => setNotice('无法读取模型连接，请刷新重试。'));}, []);
  const save = async (disable = false) => {
    if (!connection) return;
    setBusy(true); setNotice('');
    const submittedKey = key;
    setKey('');
    try {
      await api.post(`/v1/model-connection/${disable ? 'disable' : 'test-and-enable'}`,
        disable ? {expected_version: connection.version} : {model, api_key: submittedKey, expected_version: connection.version});
      await load(); onChanged();
      setNotice(disable ? '已恢复组织原有的默认模型选择。' : '连接成功，已启用。新的智能体运行将使用此模型。');
    } catch (error: unknown) {
      const detail = (error as {response?: {data?: {detail?: unknown}}}).response?.data?.detail;
      setNotice(typeof detail === 'string' ? detail : '操作失败，请检查配置后重试。');
    } finally {setBusy(false);}
  };
  return <section className="rounded-2xl border border-border bg-white/90 p-5 shadow-sm" aria-label="模型连接">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-base font-semibold">模型连接</h2><p className="mt-1 text-sm text-muted-foreground">为当前组织的智能体设置模型服务。</p></div>
      <span className="rounded-full bg-muted px-3 py-1 text-xs">{connection?.enabled ? `已启用 DeepSeek · ${connection.model}` : '使用组织默认配置'}</span>
    </div>
    {!connection ? <p className="mt-4 text-sm">{notice || '正在读取配置…'}</p> : <>
      {!connection.editable ? <p className="mt-4 text-sm text-muted-foreground">组织所有者或管理员可以修改模型连接。</p> : <>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <label className="text-sm">服务商<select className="mt-2 w-full rounded-lg border border-border bg-white p-2" disabled={busy} aria-label="服务商"><option>DeepSeek</option></select></label>
          <label className="text-sm">模型<select className="mt-2 w-full rounded-lg border border-border bg-white p-2" value={model} onChange={e => setModel(e.target.value)} disabled={busy}><option value="deepseek-v4-flash">DeepSeek V4 Flash</option><option value="deepseek-v4-pro">DeepSeek V4 Pro</option></select></label>
          <label className="text-sm">API Key<input type="password" autoComplete="off" spellCheck={false} className="mt-2 w-full rounded-lg border border-border bg-white p-2" value={key} onChange={e => setKey(e.target.value)} disabled={busy} placeholder={connection.configured ? '已保存，留空保留原密钥' : '粘贴 API Key'} /></label>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">密钥加密保存在服务端。测试仅发送固定测试文本，可能产生少量 API 费用；测试通过后自动启用。</p>
        {!connection.external_allowed && <p className="mt-3 text-sm text-amber-800">当前部署未允许使用外部模型，请联系部署管理员开启后再配置。</p>}
        {!connection.encryption_ready && <p className="mt-3 text-sm text-amber-800">服务端尚未配置持久化加密所需的部署密钥，请联系部署管理员。</p>}
        <div className="mt-4 flex flex-wrap gap-3">
          <button className="rounded-full bg-primary px-5 py-2 text-sm text-primary-foreground disabled:opacity-50" disabled={busy || !connection.external_allowed || !connection.encryption_ready || (!connection.configured && !key.trim())} onClick={() => void save()}>{busy ? '处理中…' : '测试并启用'}</button>
          {connection.enabled && <button className="rounded-lg border border-border px-4 py-2 text-sm disabled:opacity-50" disabled={busy} onClick={() => void save(true)}>恢复默认配置</button>}
        </div>
      </>}
      {notice && <p role="status" className="mt-3 text-sm">{notice}</p>}
    </>}
  </section>;
}
