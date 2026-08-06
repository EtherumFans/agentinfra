// A1B-AE-R.5 — ExpertsPage
// Lists 9 Experts from /api/v1/experts + 5 Presets from /api/v1/presets.
// Surfaces External-Expert Gate (LICENCE_REQUIRED / EGRESS_DISABLED / etc)
// so users see *why* a gated Expert is offline in their region.
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Shield,
  Search,
  Bot,
  Calculator,
  Brain,
  Microscope,
  FlaskConical,
  Pill,
  Globe,
  MessageSquareText,
  Lock,
  Unlock,
  ArrowRight,
} from 'lucide-react';

import { expertsApi } from '../services/api';

const EXPERT_ICONS: Record<string, React.ElementType> = {
  'coding-expert': Bot,
  'medical-calculator': Calculator,
  memory: Brain,
  interviewing: MessageSquareText,
  pubmed: Microscope,
  'clinical-trials': FlaskConical,
  drugbank: Pill,
  posos: Pill,
  'web-search': Globe,
};

const CORTI_ALIGNMENT_LABEL: Record<string, string> = {
  CORTI_ALIGNED: 'Corti 对齐',
  CORTI_ADAPTED: 'Corti 适配',
  ICODER_ONLY: 'iCoDer 独有',
  REFERENCE: '参考实现',
};

const GATE_REASON_LABEL: Record<string, string> = {
  OK: '放行',
  LICENCE_REQUIRED: '需许可证',
  EGRESS_DISABLED: '出口未开启',
  REGION_BLOCKED: '区域受限',
  PROVIDER_OPT_IN_MISSING: '需双 Opt-in',
};

export default function ExpertsPage() {
  const [experts, setExperts] = useState<any[]>([]);
  const [presets, setPresets] = useState<any[]>([]);
  const [gateDecisions, setGateDecisions] = useState<Record<string, any>>({});
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [expertsRes, presetsRes] = await Promise.all([
          expertsApi.list(),
          expertsApi.presets(),
        ]);
        const ex = expertsRes.data?.experts || [];
        const ps = presetsRes.data?.presets || [];
        setExperts(ex);
        setPresets(ps);

        // Evaluate gate for each external expert
        const gatedKeys = ex.filter((e: any) => e.is_gated).map((e: any) => e.canonical_key);
        const decisions: Record<string, any> = {};
        await Promise.all(
          gatedKeys.map(async (k: string) => {
            try {
              const r = await expertsApi.evaluateExternalGate({ expert_key: k });
              decisions[k] = r.data;
            } catch {
              decisions[k] = { permitted: false, reason: 'EVAL_FAILED' };
            }
          })
        );
        setGateDecisions(decisions);
      } catch (e: any) {
        setError(e?.message || '加载失败');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = experts.filter((e: any) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (e.canonical_key || '').toLowerCase().includes(q) ||
      (e.name || '').toLowerCase().includes(q) ||
      (e.origin || '').toLowerCase().includes(q)
    );
  });

  return (
    <div className="flex flex-col h-full bg-muted/20">
      <div className="mx-6 mt-6 bg-background rounded-xl shadow-sm px-6 py-3 flex items-center gap-2">
        <Shield size={18} className="text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">专家注册表</span>
        <span className="text-xs text-muted-foreground ml-auto">
          {experts.length} Experts · {presets.length} Presets
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto p-6">
          <h1 className="text-lg font-semibold text-foreground mb-1">专家注册表</h1>
          <p className="text-xs text-muted-foreground mb-4">
            9 个 Expert + 5 个 Preset Agent
          </p>

          <div className="relative mb-4">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索专家 (名称 / key / 来源)"
              className="w-full pl-9 pr-3 py-2 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring/50"
            />
          </div>

          {loading && (
            <p className="text-sm text-muted-foreground text-center py-12">加载中...</p>
          )}
          {error && (
            <div className="bg-destructive/10 border border-destructive/30 rounded-lg p-4 text-sm text-destructive">
              {error}
            </div>
          )}

          {!loading && !error && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map((ex: any) => {
                const Icon = EXPERT_ICONS[ex.canonical_key] || Bot;
                const gate = gateDecisions[ex.canonical_key];
                const isGated = !!ex.is_gated;
                const preset = presets.find(
                  (p: any) =>
                    p.canonical_key === ex.canonical_key ||
                    (p.expert_ids || []).includes(ex.canonical_key)
                );
                return (
                  <div
                    key={ex.canonical_key}
                    className="bg-background rounded-xl shadow-sm p-4 flex flex-col"
                  >
                    <div className="flex items-start gap-3 mb-3">
                      <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        <Icon size={18} className="text-primary" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-semibold text-foreground truncate">
                          {ex.name}
                        </h3>
                        <p className="text-[11px] text-muted-foreground font-mono">
                          {ex.canonical_key}
                        </p>
                      </div>
                    </div>

                    <p className="text-xs text-muted-foreground line-clamp-2 mb-3 min-h-[2rem]">
                      {ex.description || '—'}
                    </p>

                    <div className="flex flex-wrap items-center gap-1.5 mb-3 text-[10px]">
                      <span className="px-1.5 py-0.5 rounded bg-accent text-muted-foreground">
                        {CORTI_ALIGNMENT_LABEL[ex.corti_alignment] || ex.corti_alignment}
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-accent text-muted-foreground">
                        {ex.origin}
                      </span>
                      {isGated && (
                        <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 flex items-center gap-0.5">
                          <Lock size={10} /> gated
                        </span>
                      )}
                      {!isGated && (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 flex items-center gap-0.5">
                          <Unlock size={10} /> open
                        </span>
                      )}
                    </div>

                    {isGated && gate && (
                      <div
                        className={`text-[10px] px-2 py-1 rounded mb-3 ${
                          gate.permitted
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-amber-50 text-amber-700'
                        }`}
                      >
                        外部出口: {GATE_REASON_LABEL[gate.reason] || gate.reason}
                      </div>
                    )}

                    {preset && (
                      <Link
                        to={`/ai-studio/agents/new?from_preset=${encodeURIComponent(preset.preset_key || preset.id)}`}
                        className="mt-auto text-xs text-primary hover:underline flex items-center gap-1"
                      >
                        从 Preset 创建 <ArrowRight size={11} />
                      </Link>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Preset catalogue */}
          {!loading && !error && presets.length > 0 && (
            <div className="mt-10">
              <h2 className="text-sm font-semibold text-foreground mb-3">
                Preset Agent 目录 ({presets.length})
              </h2>
              <div className="bg-background rounded-xl shadow-sm divide-y divide-border">
                {presets.map((p: any) => (
                  <div key={p.preset_key || p.id} className="px-4 py-3 flex items-center gap-3">
                    <Bot size={16} className="text-muted-foreground shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground">{p.name}</p>
                      <p className="text-[11px] text-muted-foreground truncate">
                        {p.description}
                      </p>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-muted-foreground">
                      {p.delegates_to_pack ? '已物化' : '未物化'}
                    </span>
                    <Link
                      to={`/ai-studio/agents/new?from_preset=${encodeURIComponent(p.preset_key || p.id)}`}
                      className="text-xs text-primary hover:underline flex items-center gap-1 shrink-0"
                    >
                      克隆 <ArrowRight size={11} />
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
