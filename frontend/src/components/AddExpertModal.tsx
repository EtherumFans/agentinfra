// iCoDer — 添加自定义专家模态框
import { useState } from 'react';
import { X, Plus, Trash2, Info } from 'lucide-react';
import { expertsApi } from '../services/api';

interface McpServerDraft {
  id: string;
  name: string;
  url: string;
  transport_type: string;
  description: string;
}

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

const CATEGORIES = [
  { value: 'coding', label: '医学编码' },
  { value: 'medication', label: '药物' },
  { value: 'search', label: '文献与搜索' },
  { value: 'utility', label: '工具' },
  { value: 'interview', label: '问诊' },
  { value: 'general', label: '通用' },
];

const ICONS = ['Bot', 'Globe', 'BrainCircuit', 'Pill', 'FlaskConical', 'Database', 'BookOpenText', 'Calculator', 'Stethoscope', 'MessageSquareText', 'Search'];

export default function AddExpertModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [icon, setIcon] = useState('Bot');
  const [category, setCategory] = useState('general');
  const [mcpServers, setMcpServers] = useState<McpServerDraft[]>([{ id: '1', name: '', url: '', transport_type: 'streamable_http', description: '' }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleAddMcpServer = () => {
    setMcpServers([...mcpServers, { id: String(Date.now()), name: '', url: '', transport_type: 'streamable_http', description: '' }]);
  };

  const handleRemoveMcpServer = (id: string) => {
    if (mcpServers.length <= 1) return;
    setMcpServers(mcpServers.filter(s => s.id !== id));
  };

  const handleUpdateMcp = (id: string, field: keyof McpServerDraft, value: string) => {
    setMcpServers(mcpServers.map(s => s.id === id ? { ...s, [field]: value } : s));
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('请输入专家名称');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const validMcpServers = mcpServers.filter(s => s.name.trim() && s.url.trim());
      await expertsApi.create({
        name: name.trim(),
        description: description.trim(),
        system_prompt: systemPrompt.trim(),
        icon,
        category,
        mcp_servers: validMcpServers.map(s => ({
          name: s.name.trim(),
          url: s.url.trim(),
          transport_type: s.transport_type,
          description: s.description.trim(),
        })),
      });
      onCreated();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '创建专家失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-card rounded-xl border border-border shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h2 className="text-base font-semibold text-foreground">添加自定义专家</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-accent transition-colors">
            <X size={16} className="text-muted-foreground" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Expert Name */}
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">专家名称</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="请输入专家名称"
              className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20 focus:border-ring transition-colors"
              autoFocus
            />
          </div>

          {/* Description */}
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="描述该专家的用途和能力"
              className="w-full h-20 resize-none border border-border rounded-lg p-3 text-sm bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Icon + Category */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium text-foreground block mb-1">图标</label>
              <select value={icon} onChange={(e) => setIcon(e.target.value)} className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20 focus:border-ring transition-colors">
                {ICONS.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-foreground block mb-1">分类</label>
              <select value={category} onChange={(e) => setCategory(e.target.value)} className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20 focus:border-ring transition-colors">
                {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
          </div>

          {/* System Prompt */}
          <div>
            <label className="text-sm font-medium text-foreground block mb-1 flex items-center gap-1.5">
              系统提示词
              <Info size={12} className="text-muted-foreground cursor-help" />
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="请输入系统提示词"
              className="w-full h-32 resize-none border border-border rounded-lg p-3 text-sm font-mono bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* MCP Servers */}
          <div>
            <label className="text-sm font-medium text-foreground block mb-1 flex items-center gap-1.5">
              MCP 服务器（可选）
              <Info size={12} className="text-muted-foreground cursor-help" />
            </label>

            <div className="space-y-3">
              {mcpServers.map((srv) => (
                <div key={srv.id} className="border border-border rounded-lg p-3 space-y-2 bg-muted/20">
                  <div className="flex items-center gap-2">
                    <input
                      value={srv.name}
                      onChange={(e) => handleUpdateMcp(srv.id, 'name', e.target.value)}
                      placeholder="例如：my-mcp-server"
                      className="flex-1 text-xs border border-border rounded-md px-2 py-1.5 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                    {mcpServers.length > 1 && (
                      <button onClick={() => handleRemoveMcpServer(srv.id)} className="p-1 text-red-400 hover:text-red-600 rounded hover:bg-red-50">
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                  <input
                    value={srv.url}
                    onChange={(e) => handleUpdateMcp(srv.id, 'url', e.target.value)}
                    placeholder="https://example.com/mcp"
                    className="w-full text-xs border border-border rounded-md px-2 py-1.5 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring font-mono"
                  />
                  <select
                    value={srv.transport_type}
                    onChange={(e) => handleUpdateMcp(srv.id, 'transport_type', e.target.value)}
                    className="w-full text-xs border border-border rounded-md px-2 py-1.5 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    <option value="streamable_http">streamable_http</option>
                    <option value="stdio">stdio</option>
                    <option value="sse">sse</option>
                  </select>
                </div>
              ))}

              <button
                onClick={handleAddMcpServer}
                className="text-xs text-primary hover:underline flex items-center gap-1"
              >
                <Plus size={12} /> 新建 MCP 服务器
              </button>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
            <button onClick={onClose} className="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium rounded-lg transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground text-sm px-4 py-2 min-h-[2.75rem]">取消</button>
            <button
              onClick={handleSubmit}
              disabled={saving || !name.trim()}
              className="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium rounded-lg transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring bg-primary text-primary-foreground hover:bg-primary/90 text-sm px-5 py-2 min-h-[2.75rem] disabled:opacity-50"
            >
              {saving ? <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : null}
              {saving ? '添加中...' : '添加专家'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
