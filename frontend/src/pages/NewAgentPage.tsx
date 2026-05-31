// iCoDer New Agent Page — iCoDer Console 1:1
// /ai-studio/agents/new: "Start from scratch" + "Use a template"
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useT } from '../i18n';
import {
  Bot, Search, BookOpen, Sparkles,
  Stethoscope, BookOpenText, Shield, CheckCircle,
  ClipboardList, FileText, AlertTriangle, ClipboardCheck,
  Pill, FileWarning, GraduationCap, Users, FileCheck,
  Send, FileSearch, ChevronRight,
} from 'lucide-react';
import { agentsApi, expertsApi } from '../services/api';

const ICON_MAP: Record<string, React.ElementType> = {
  Bot, BookOpenText, Shield, CheckCircle, Stethoscope,
  ClipboardList, FileText, AlertTriangle, ClipboardCheck,
  Pill, FileWarning, GraduationCap, Users, FileCheck,
  Send, BookOpen, FileSearch, Sparkles,
};


export default function NewAgentPage() {
  const navigate = useNavigate();
  const t = useT();
  const [templates, setTemplates] = useState<any[]>([]);
  const [expertNameToId, setExpertNameToId] = useState<Record<string, string>>({});
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [templateSearch, setTemplateSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [scratchName, setScratchName] = useState('');
  const [showScratchInput, setShowScratchInput] = useState(false);

  useEffect(() => {
    agentsApi.templates().then(r => {
      setTemplates(r.data?.templates || []);
    }).catch(() => {});
    expertsApi.list('', '', 'all').then(r => {
      const experts = r.data?.experts || [];
      const nameMap: Record<string, string> = {};
      for (const e of experts) nameMap[e.name] = e.id;
      setExpertNameToId(nameMap);
    }).catch(() => {});
  }, []);

  const selected = templates.find((t: any) => t.id === selectedTemplate);
  const filteredTemplates = templates.filter((t: any) => {
    if (!templateSearch) return true;
    const q = templateSearch.toLowerCase();
    return (t.title || '').toLowerCase().includes(q)
      || (t.description || '').toLowerCase().includes(q)
      || (t.category || '').toLowerCase().includes(q);
  });

  const handleStartFromScratch = async () => {
    if (showScratchInput) {
      if (!scratchName.trim()) return;
      setCreating(true);
      try {
        const res = await agentsApi.create({
          name: scratchName.trim(),
          description: '',
          system_prompt: '<role>\n</role>\n\n<output_format>\n</output_format>',
          category: '编码',
          expert_ids: [],
          config: {},
        });
        navigate(`/ai-studio/agents/${res.data.id}`, { state: { newAgent: true } });
      } catch (err) {
        console.error('Failed to create agent', err);
        setCreating(false);
      }
    } else {
      setShowScratchInput(true);
    }
  };

  const handleCreateFromTemplate = async () => {
    if (!selected) return;
    setCreating(true);
    try {
      const expertIds = (selected.expert_ids || [])
        .map((name: string) => expertNameToId[name])
        .filter(Boolean);
      const res = await agentsApi.create({
        name: selected.title,
        description: selected.description,
        system_prompt: selected.system_prompt || '',
        category: selected.category || '编码',
        expert_ids: expertIds,
        config: selected.config || {},
      });
      const agent = res.data;
      navigate(`/ai-studio/agents/${agent.id}`, { state: { newAgent: true } });
    } catch (err) {
      console.error('Failed to create agent from template', err);
      setCreating(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-muted/20">
      {/* Header */}
      <div className="mx-6 mt-6 bg-background rounded-xl shadow-sm ring-1 ring-border/20 px-6 py-3 flex items-center gap-2">
        <Bot size={18} className="text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">AI智能体</span>
        <ChevronRight size={14} className="text-muted-foreground" />
        <span className="text-sm text-foreground">新建</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto p-6">
          <h1 className="text-lg font-semibold text-foreground mb-1">创建AI智能体</h1>
          <p className="text-xs text-muted-foreground mb-6">
            构建医疗AI智能体，在您的业务系统中执行任务
          </p>

          <div className="grid grid-cols-2 gap-8">
            {/* Left: Templates */}
            <div className="space-y-6">
              {/* Start from scratch */}
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5 hover:ring-primary/30 transition-all">
                <h2 className="text-sm font-semibold text-foreground mb-1">从零开始创建</h2>
                <p className="text-xs text-muted-foreground mb-3">
                  从头配置您的AI智能体
                </p>
                {showScratchInput && (
                  <div className="mb-3">
                    <input
                      value={scratchName}
                      onChange={e => setScratchName(e.target.value)}
                      placeholder="AI智能体名称"
                      className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
                      autoFocus
                      onKeyDown={e => { if (e.key === 'Enter') handleStartFromScratch(); }}
                    />
                  </div>
                )}
                <button
                  onClick={handleStartFromScratch}
                  disabled={creating || (showScratchInput && !scratchName.trim())}
                  className="text-xs px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50"
                >
                  {creating && showScratchInput ? '创建中...' : '创建AI智能体'}
                </button>
                {showScratchInput && (
                  <button
                    onClick={() => setShowScratchInput(false)}
                    className="text-xs px-4 py-2 text-muted-foreground hover:text-foreground ml-2 transition-colors"
                  >
                    取消
                  </button>
                )}
              </div>

              {/* Use a template */}
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 overflow-hidden">
                <div className="px-5 py-4 border-b border-border">
                  <h2 className="text-sm font-semibold text-foreground mb-1">使用模板</h2>
                  <p className="text-xs text-muted-foreground">
                    从预配置的AI智能体开始
                  </p>
                </div>
                <div className="px-5 py-3">
                  <div className="relative">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      value={templateSearch}
                      onChange={e => setTemplateSearch(e.target.value)}
                      placeholder="搜索模板"
                      className="w-full pl-9 pr-3 py-2 text-xs bg-muted/30 border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                </div>
                <div className="max-h-96 overflow-y-auto px-5 pb-4 space-y-1">
                  {filteredTemplates.map((tpl: any) => {
                    const Icon = ICON_MAP[tpl.icon] || Bot;
                    const isSelected = selectedTemplate === tpl.id;
                    return (
                      <label
                        key={tpl.id}
                        className={`flex items-start gap-3 px-3 py-3 rounded-lg cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-primary/10 border border-primary/30'
                            : 'hover:bg-accent border border-transparent'
                        }`}
                      >
                        <input
                          type="radio"
                          name="agent-template"
                          className="mt-0.5 accent-primary shrink-0"
                          checked={isSelected}
                          onChange={() => setSelectedTemplate(tpl.id)}
                        />
                        <Icon size={20} className="text-muted-foreground shrink-0 mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-foreground">{tpl.title}</p>
                            {tpl.category && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-accent/70 text-muted-foreground`}>
                                {tpl.category}
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                            {tpl.description}
                          </p>
                          {(tpl.expert_ids || []).length > 0 && (
                            <p className="text-[10px] text-muted-foreground mt-1">
                              {(tpl.expert_ids || []).length}个专家已预配置
                            </p>
                          )}
                        </div>
                      </label>
                    );
                  })}
                  {filteredTemplates.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-4">
                      {templates.length === 0 ? '加载模板中...' : '未找到匹配的模板'}
                    </p>
                  )}
                </div>
              </div>

              {selected && (
                <div className="flex justify-end">
                  <button
                    onClick={handleCreateFromTemplate}
                    disabled={creating}
                    className="text-xs px-5 py-2.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50"
                  >
                    {creating ? '创建中...' : `创建 "${selected.title}"`}
                  </button>
                </div>
              )}
            </div>

            {/* Right: Preview */}
            <div className="space-y-6">
              {selected ? (
                <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-6">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">AI智能体预览</h3>
                  </div>
                  <h2 className="text-base font-semibold text-foreground mb-2">{selected.title}</h2>
                  <p className="text-xs text-muted-foreground mb-4">{selected.description}</p>

                  {selected.category && (
                    <div className="flex items-center gap-2 mb-4">
                      <span className="text-[10px] text-muted-foreground">分类：</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-accent/70 text-muted-foreground`}>
                        {selected.category}
                      </span>
                    </div>
                  )}

                  {(selected.expert_ids || []).length > 0 && (
                    <div className="mb-4">
                      <span className="text-[10px] text-muted-foreground block mb-1.5">
                        预配置专家 ({selected.expert_ids.length}):
                      </span>
                      <div className="flex flex-wrap gap-1">
                        {selected.expert_ids.map((name: string) => (
                          <span key={name} className="text-[10px] px-2 py-0.5 bg-accent rounded-full text-muted-foreground">
                            {name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {selected.system_prompt && (
                    <div className="mt-4">
                      <span className="text-[10px] text-muted-foreground block mb-1.5">系统提示词预览:</span>
                      <div className="bg-muted/20 rounded-lg p-3 max-h-48 overflow-y-auto">
                        <pre className="text-[10px] text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed">
                          {selected.system_prompt.slice(0, 500)}
                          {selected.system_prompt.length > 500 ? '\n...' : ''}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-6 flex flex-col items-center justify-center min-h-[300px]">
                  <Bot size={40} className="text-muted-foreground/30 mb-3" />
                  <p className="text-sm text-muted-foreground text-center">
                    选择模板以预览
                  </p>
                  <p className="text-[11px] text-muted-foreground/60 text-center mt-1">
                    或从零开始创建自定义AI智能体
                  </p>
                </div>
              )}

              {/* Info */}
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
                <div className="flex items-start gap-3">
                  <Sparkles size={16} className="text-muted-foreground shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-medium text-foreground mb-1">与AI智能体对话将消耗额度</p>
                    <p className="text-[10px] text-muted-foreground">
                      每条消息根据涉及的专家数量和响应复杂度消耗相应额度。
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
