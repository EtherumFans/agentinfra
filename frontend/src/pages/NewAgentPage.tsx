// iCoDer New Agent Page - iCoDer Console 1:1
// /ai-studio/agents/new: "Start from scratch" + "Use a template"
// A1B-AE-R.5: also supports ?from_preset=<key> (Preset clone flow).
import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Bot, Search, BookOpen, Sparkles,
  Stethoscope, BookOpenText, Shield, CheckCircle,
  ClipboardList, FileText, AlertTriangle, ClipboardCheck,
  Pill, FileWarning, GraduationCap, Users, FileCheck,
  Send, FileSearch, ChevronRight, Plus, Lightbulb, ArrowRight,
} from 'lucide-react';

import { useT } from '../i18n';
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
  const [searchParams] = useSearchParams();
  const fromPreset = searchParams.get('from_preset') || '';
  const [templates, setTemplates] = useState<any[]>([]);
  const [expertNameToId, setExpertNameToId] = useState<Record<string, string>>({});
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [templateSearch, setTemplateSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [scratchName, setScratchName] = useState('');
  const [showScratchInput, setShowScratchInput] = useState(false);
  const [presetInfo, setPresetInfo] = useState<any | null>(null);
  const [presetError, setPresetError] = useState<string | null>(null);

  useEffect(() => {
    agentsApi.templates().then(r => {
      setTemplates(r.data?.templates || []);
    }).catch(() => {});
    // experts endpoint deleted in Phase 2.1-B Step 1; expertNameToId stays empty
  }, []);

  // A1B-AE-R.5 — when ?from_preset=... is supplied, load preset info
  useEffect(() => {
    if (!fromPreset) {
      setPresetInfo(null);
      return;
    }
    expertsApi
      .presets()
      .then((r) => {
        const list = r.data?.presets || [];
        const found =
          list.find((p: any) => (p.preset_key || p.id) === fromPreset) || null;
        if (!found) {
          setPresetError(`未找到 Preset: ${fromPreset}`);
        } else {
          setPresetInfo(found);
        }
      })
      .catch(() => setPresetError('加载 Preset 列表失败'));
  }, [fromPreset]);

  const handleCreateFromPreset = async () => {
    if (!fromPreset) return;
    setCreating(true);
    try {
      const res = await agentsApi.quickFromPreset(fromPreset, {
        name: presetInfo?.name,
      });
      const agent = res.data?.agent || res.data;
      navigate(`/ai-studio/agents/${agent.id}`, { state: { newAgent: true } });
    } catch (err: any) {
      console.error('Failed to create agent from preset', err);
      setPresetError(err?.response?.data?.detail || '从 Preset 创建失败');
      setCreating(false);
    }
  };

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
      <div className="mx-6 mt-6 bg-background rounded-xl shadow-sm px-6 py-3 flex items-center gap-2">
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

          {/* A1B-AE-R.5 — Preset clone banner */}
          {fromPreset && (
            <div className="mb-6 bg-primary/5 border border-primary/30 rounded-xl p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground mb-1">
                    从 Preset 克隆: {fromPreset}
                  </p>
                  {presetError && (
                    <p className="text-xs text-destructive">{presetError}</p>
                  )}
                  {presetInfo && (
                    <div className="text-xs text-muted-foreground space-y-1">
                      <p>
                        <strong className="text-foreground">{presetInfo.name}</strong> —{' '}
                        {presetInfo.description}
                      </p>
                      <p>
                        delegates_to_pack:{' '}
                        <code className="text-[10px] bg-accent px-1 py-0.5 rounded">
                          {presetInfo.delegates_to_pack || '(null)'}
                        </code>
                      </p>
                    </div>
                  )}
                </div>
                <button
                  onClick={handleCreateFromPreset}
                  disabled={creating || !presetInfo}
                  className="shrink-0 text-xs px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium disabled:opacity-50"
                >
                  {creating ? '克隆中...' : '克隆到我的 Agent'}
                </button>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-8">
            {/* Left: Templates */}
            <div className="space-y-6">
              {/* Start from scratch */}
              <div className="bg-background rounded-xl shadow-sm p-5 hover:ring-primary/30 transition-all">
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
                      className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring/50"
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
              <div className="bg-background rounded-xl shadow-sm overflow-hidden">
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
                <div className="bg-background rounded-xl shadow-sm p-6">
                  {/* Title + Customize agent (Corti: same row) */}
                  <div className="flex items-start justify-between gap-3 mb-6">
                    <div className="min-w-0 flex-1">
                      <h2 className="text-base font-semibold text-foreground mb-2">{selected.title}</h2>
                      <p className="text-xs text-muted-foreground">{selected.description}</p>
                    </div>
                    <button
                      onClick={handleCreateFromTemplate}
                      disabled={creating}
                      className="shrink-0 inline-flex items-center gap-1.5 text-xs px-3 py-2 bg-foreground text-background rounded-lg hover:opacity-90 transition-opacity font-medium disabled:opacity-50"
                    >
                      {t.customizeAgent}
                      <ArrowRight size={12} />
                    </button>
                  </div>

                  {/* Chat-style preview (Corti: Ask the agent...) */}
                  <div className="flex flex-col items-center justify-center py-8">
                    <p className="text-3xl font-semibold text-foreground tracking-tight mb-6">
                      {t.askTheAgent}
                    </p>
                    <div className="w-full max-w-md">
                      <div className="relative bg-background rounded-2xl ring-1 ring-border/40 focus-within:ring-2 focus-within:ring-ring/50 transition-shadow">
                        <textarea
                          placeholder={t.agentInputPlaceholder}
                          rows={2}
                          className="w-full resize-none bg-transparent text-sm text-foreground placeholder:text-foreground/70 px-4 pt-3 pb-10 focus:outline-none rounded-2xl"
                          onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault();
                              handleCreateFromTemplate();
                            }
                          }}
                        />
                        <div className="absolute left-3 bottom-2">
                          <button
                            type="button"
                            className="inline-flex items-center justify-center w-7 h-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                            aria-label="attach"
                          >
                            <Plus size={14} />
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center justify-end gap-1 mt-2">
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors px-2 py-1"
                        >
                          <Plus size={11} /> {t.addContext}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Helper chips (Corti: What can you do? / Suggest prompt) */}
                  <div className="flex items-center justify-center gap-4 pt-6 border-t border-border/40">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <Lightbulb size={12} />
                      {t.whatCanYouDo}
                    </button>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <Sparkles size={12} />
                      {t.suggestPrompt}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-background rounded-xl shadow-sm p-6 flex flex-col items-center justify-center min-h-[300px]">
                  <Bot size={40} className="text-muted-foreground/30 mb-3" />
                  <p className="text-sm text-muted-foreground text-center">
                    选择模板以预览
                  </p>
                  <p className="text-[11px] text-muted-foreground/60 text-center mt-1">
                    或从零开始创建自定义AI智能体
                  </p>
                </div>
              )}

              {/* Credit reminder (Corti bottom gray) */}
              <div className="text-center pt-1">
                <p className="text-[10px] text-muted-foreground/70">{t.messagingConsumesCredits}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
