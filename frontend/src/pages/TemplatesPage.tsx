// iCoDer - Templates (Beta) page
//
// IA:
//   Header  Templates · "Manage templates and sections for generating
//           structured documents"
//   CTA     Template builder (right-aligned, opens builder modal)
//   Banner  "Templates (beta) is powered by the new templates and
//           sections API" + Provide feedback (stub)
//   View    Templates / Sections (radio toggle; Sections stub for now)
//   Filters Search + Language combobox + All types + Filter
//   Cards   Name + Description · builtin badge · scope badge · 3-dot menu
//
// iCoDer extension: Templates seeded with 9 Chinese clinical templates
// (inpatient / surgery / outpatient / emergency / consultation) so users
// see a real library out of the box; CN-language combobox default.
import { useEffect, useState, useCallback } from 'react';
import {
  Loader2, Plus, Search, X, ExternalLink, FileText, MoreVertical,
  Sparkles, MessageSquareWarning,
} from 'lucide-react';

import { templatesApi } from '../services/api';
import { useT } from '../i18n';

interface Template {
  id: string;
  name: string;
  description: string;
  content: string;
  category: string;
  language: string;
  is_builtin: boolean;
  scope: string;
  created_at: string | null;
  updated_at: string | null;
}

type View = 'templates' | 'sections';
type CategoryFilter = '' | 'inpatient' | 'surgery' | 'outpatient' | 'emergency' | 'consultation' | 'custom';
type LanguageFilter = '' | 'zh-CN' | 'en-US';
type SortKey = 'recent' | 'name';

const CATEGORY_LABEL_KEY: Record<string, string> = {
  inpatient: 'templateCategoryInpatient',
  surgery: 'templateCategorySurgery',
  outpatient: 'templateCategoryOutpatient',
  emergency: 'templateCategoryEmergency',
  consultation: 'templateCategoryConsultation',
  custom: 'templateCategoryCustom',
};

export default function TemplatesPage() {
  const t = useT();
  const [view, setView] = useState<View>('templates');
  const [items, setItems] = useState<Template[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<CategoryFilter>('');
  const [language, setLanguage] = useState<LanguageFilter>('');
  const [page, setPage] = useState(1);
  const [showBuilder, setShowBuilder] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await templatesApi.list({
        search: search.trim(),
        category,
        language,
        page,
        page_size: 50, // Templates Beta is a content library, not a heavy table
      });
      setItems(res.data.templates || []);
      setTotal(res.data.total || 0);
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || err?.message || '加载模板失败');
    } finally {
      setLoading(false);
    }
  }, [search, category, language, page]);

  useEffect(() => { fetchList(); }, [fetchList]);
  useEffect(() => { setPage(1); }, [search, category, language]);

  return (
    <div className="bg-muted/20 min-h-dvh p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <h2 className="text-2xl font-bold text-foreground">{t.templatesTitle}</h2>
            <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-300 ring-1 ring-amber-500/20">
              Beta
            </span>
          </div>
          <p className="text-sm text-muted-foreground max-w-2xl">{t.templatesDesc}</p>
        </div>
        <button
          onClick={() => setShowBuilder(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors shadow-sm"
        >
          <Plus size={14} />
          {t.templateBuilder}
          <ExternalLink size={12} className="opacity-70" />
        </button>
      </div>

      {/* Beta banner */}
      <div className="mb-5 px-4 py-3 rounded-lg bg-amber-500/5 ring-1 ring-amber-500/20 text-sm flex items-start gap-3">
        <Sparkles size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="flex-1 text-amber-900 dark:text-amber-200">
          <span>Templates (beta) is powered by the </span>
          <span className="font-medium underline underline-offset-2">new templates and sections API</span>.
          <span className="ml-1">Please let us know what you'd like to see here or report any issues.</span>
        </div>
        <button className="text-xs px-3 py-1 rounded-md bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-300 transition-colors">
          Provide feedback
        </button>
      </div>

      {/* View toggle + filters */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        {/* View radio group */}
        <div className="inline-flex items-center rounded-lg border border-border/20 bg-background p-0.5">
          {(['templates', 'sections'] as View[]).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                view === v ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {v === 'templates' ? t.viewTemplates : t.viewSections}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <div className="relative w-full max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t.searchTemplatesPlaceholder}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <select
          value={language}
          onChange={e => setLanguage(e.target.value as LanguageFilter)}
          className="appearance-none text-sm pl-3 pr-8 py-2 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer hover:border-primary/30 focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">{t.allTypes}</option>
          <option value="zh-CN">中文 (zh-CN)</option>
          <option value="en-US">English (en-US)</option>
        </select>
        <button
          className="inline-flex items-center gap-1 px-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground hover:bg-accent transition-colors"
        >
          {t.filter}
        </button>
      </div>

      {/* Sections view stub */}
      {view === 'sections' ? (
        <div className="bg-background rounded-xl shadow-sm p-12 text-center">
          <FileText size={32} className="mx-auto mb-3 text-muted-foreground opacity-40" />
          <p className="text-sm text-muted-foreground mb-1 font-medium">{t.viewSections}</p>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            Reusable chunks that compose into templates. Coming soon.
          </p>
        </div>
      ) : (
        <>
          {/* Card grid */}
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="bg-background rounded-xl p-8 text-center shadow-sm">
              <MessageSquareWarning size={28} className="mx-auto mb-3 text-destructive opacity-60" />
              <p className="text-sm text-destructive mb-4">{error}</p>
              <button onClick={fetchList} className="bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">重试</button>
            </div>
          ) : items.length === 0 ? (
            <div className="bg-background rounded-xl p-12 text-center shadow-sm">
              <FileText size={32} className="mx-auto mb-3 text-muted-foreground opacity-40" />
              <p className="text-sm text-muted-foreground mb-4">{t.noTemplates}</p>
              <button
                onClick={() => setShowBuilder(true)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                <Plus size={14} /> {t.templateBuilder}
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {items.map(tpl => (
                <TemplateCard
                  key={tpl.id}
                  template={tpl}
                  onDeleted={fetchList}
                />
              ))}
            </div>
          )}

          {/* Counter footer (no hard pagination in Beta) */}
          {!loading && !error && items.length > 0 && (
            <p className="text-xs text-muted-foreground mt-4 text-right">
              {items.length} / {total}
            </p>
          )}
        </>
      )}

      {showBuilder && (
        <TemplateBuilderModal
          onClose={() => setShowBuilder(false)}
          onCreated={() => { setShowBuilder(false); fetchList(); }}
        />
      )}
    </div>
  );
}

function TemplateCard({ template, onDeleted }: { template: Template; onDeleted: () => void; }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const categoryLabel = CATEGORY_LABEL_KEY[template.category]
    ? t[CATEGORY_LABEL_KEY[template.category] as keyof typeof t] as string
    : template.category;

  async function handleDelete() {
    if (!confirm(`Delete template "${template.name}"? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await templatesApi.delete(template.id);
      onDeleted();
    } catch {
      // toast handled by interceptor
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="group bg-background rounded-xl shadow-sm p-5 hover:ring-primary/30 transition-all flex flex-col">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-foreground truncate">{template.name}</h3>
          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{template.description}</p>
        </div>
        <button className="p-1 rounded-md text-muted-foreground hover:bg-accent opacity-0 group-hover:opacity-100 transition-opacity">
          <MoreVertical size={14} />
        </button>
      </div>
      <div className="flex items-center gap-2 mt-auto pt-2 flex-wrap">
        {template.is_builtin && (
          <span className="inline-flex items-center text-[10px] font-semibold uppercase tracking-wider rounded px-1.5 py-0.5 bg-primary/10 text-primary ring-1 ring-primary/20">
            {t.builtinBadge}
          </span>
        )}
        <span className="inline-flex items-center text-[10px] font-medium rounded px-1.5 py-0.5 bg-muted text-muted-foreground ring-1 ring-border">
          {categoryLabel}
        </span>
        <span className="inline-flex items-center text-[10px] font-medium rounded px-1.5 py-0.5 bg-muted text-muted-foreground ring-1 ring-border">
          {t.scopeAllCustomers}
        </span>
        <span className="ml-auto inline-flex items-center text-[10px] text-muted-foreground">
          {template.language}
        </span>
      </div>
      {!template.is_builtin && (
        <div className="flex items-center justify-end mt-2 pt-2 border-t border-border/10">
          <button
            onClick={handleDelete}
            disabled={busy}
            className="text-xs text-muted-foreground hover:text-destructive transition-colors disabled:opacity-40"
          >
            {busy ? <Loader2 size={12} className="inline animate-spin mr-1" /> : null}
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function TemplateBuilderModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void; }) {
  const t = useT();
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('custom');
  const [language, setLanguage] = useState<'zh-CN' | 'en-US'>('zh-CN');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  async function submit() {
    if (!name.trim()) {
      setFormError('请填写模板名称');
      return;
    }
    setSubmitting(true);
    setFormError('');
    try {
      await templatesApi.create({
        name: name.trim(),
        description: desc.trim(),
        content,
        category,
        language,
      });
      onCreated();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setFormError(typeof detail === 'string' ? detail : detail?.message || '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-background rounded-xl shadow-2xl shadow-sm w-full max-w-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-border/20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">{t.templateBuilder}</h3>
            <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300 ring-1 ring-amber-500/20">Beta</span>
          </div>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-accent text-muted-foreground">
            <X size={16} />
          </button>
        </div>
        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={t.templateNamePlaceholder}
              autoFocus
              className="w-full px-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Description</label>
            <input
              value={desc}
              onChange={e => setDesc(e.target.value)}
              placeholder={t.templateDescPlaceholder}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-foreground mb-1.5">{t.templateCategory}</label>
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                className="w-full appearance-none text-sm pl-3 pr-8 py-2 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="inpatient">{t.templateCategoryInpatient}</option>
                <option value="surgery">{t.templateCategorySurgery}</option>
                <option value="outpatient">{t.templateCategoryOutpatient}</option>
                <option value="emergency">{t.templateCategoryEmergency}</option>
                <option value="consultation">{t.templateCategoryConsultation}</option>
                <option value="custom">{t.templateCategoryCustom}</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-foreground mb-1.5">{t.templateLanguage}</label>
              <select
                value={language}
                onChange={e => setLanguage(e.target.value as 'zh-CN' | 'en-US')}
                className="w-full appearance-none text-sm pl-3 pr-8 py-2 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="zh-CN">{t.templateLanguageZh}</option>
                <option value="en-US">{t.templateLanguageEn}</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Content</label>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder={t.templateContentPlaceholder}
              rows={8}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-y font-mono"
            />
          </div>
          {formError && (
            <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{formError}</p>
          )}
        </div>
        <div className="px-5 py-3 border-t border-border/20 bg-muted/30 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-border/20 text-foreground hover:bg-accent transition-colors"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {submitting && <Loader2 size={12} className="animate-spin" />}
            {t.createTemplate}
          </button>
        </div>
      </div>
    </div>
  );
}