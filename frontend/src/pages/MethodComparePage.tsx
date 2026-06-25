// Phase B — MethodComparePage
//
// Workbench for running N coding methods on the same EMR text and
// comparing results side-by-side. Backed by /api/icoder/coding-review/compare
// + /api/icoder/coding-methods/list.
//
// Use cases:
//   - ablation studies (4 MedCodER variants vs 4 legacy methods)
//   - shadow-comparison tests (production + candidate side-by-side)
//   - QA review (consensus_primary_code aggregation across methods)

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Play, RefreshCw, AlertTriangle } from 'lucide-react';
import { icoderCodingReviewApi } from '../services/icoderCodingReviewApi';
import {
  MethodComparisonGrid,
  MethodTraceViewer,
} from '../components/medical-coding/MethodTraceViewer';
import type {
  CodingMethodInfo,
  CompareResponse,
  ListMethodsResponse,
} from '../types/runtime';

const DEFAULT_METHOD_IDS = [
  'medcoder.full',
  'medcoder.prompt+retrieve',
  'legacy.deepseek',
  'noop.unavailable',
];

const SAMPLE_EMR = `患者男性，68岁，因"反复胸闷、胸痛1月余，加重3天"入院。
入院查体：BP 152/95 mmHg，心率 88 次/分，心律齐，双肺呼吸音清。
既往史：高血压病史10年，糖尿病史5年，否认肝炎、结核等传染病史。
辅助检查：心电图示 ST 段压低；心肌酶谱 CK-MB 升高；肌钙蛋白 I 阳性。
入院诊断：1. 冠心病 不稳定型心绞痛 2. 原发性高血压 3. 2 型糖尿病
诊疗经过：行冠状动脉造影 + PCI 支架置入术，术后恢复良好。
出院诊断：1. 急性 ST 段抬高型心肌梗死 (I21.0) 2. 高血压 3. 2型糖尿病
手术操作：经皮冠状动脉支架置入术 (00.66)`;

export default function MethodComparePage() {
  const [methodsList, setMethodsList] = useState<ListMethodsResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>(DEFAULT_METHOD_IDS);
  const [emrText, setEmrText] = useState(SAMPLE_EMR);
  const [caseId, setCaseId] = useState('demo-case-001');
  const [response, setResponse] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    icoderCodingReviewApi
      .listMethods()
      .then((data) => {
        if (!cancelled) setMethodsList(data);
      })
      .catch((e) => {
        if (!cancelled) setError(`Failed to load methods: ${e.message}`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleMethod = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= 8 ? prev : [...prev, id],
    );
  }, []);

  const runCompare = useCallback(async () => {
    if (!emrText.trim()) {
      setError('EMR text is empty');
      return;
    }
    if (selectedIds.length === 0) {
      setError('Select at least one method');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const resp = await icoderCodingReviewApi.compareMethods({
        emr_text: emrText,
        method_ids: selectedIds,
        case_id: caseId,
      });
      setResponse(resp);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [emrText, selectedIds, caseId]);

  const groupedByFamily = useMemo(() => {
    if (!methodsList) return new Map<string, CodingMethodInfo[]>();
    const out = new Map<string, CodingMethodInfo[]>();
    for (const m of methodsList.methods) {
      const arr = out.get(m.method_family) ?? [];
      arr.push(m);
      out.set(m.method_family, arr);
    }
    return out;
  }, [methodsList]);

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-900">Method Compare</h1>
        <p className="mt-1 text-sm text-slate-600">
          Run multiple coding methods on the same EMR text and compare results side-by-side.
          Backed by{' '}
          <code className="rounded bg-slate-200 px-1 py-0.5 text-xs">
            /api/icoder/coding-review/compare
          </code>
          .
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: input + method picker */}
        <aside className="lg:col-span-4 space-y-4">
          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Case ID
            </label>
            <input
              type="text"
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <label className="mt-3 mb-1 block text-xs font-medium text-slate-600">
              EMR Text ({emrText.length} chars)
            </label>
            <textarea
              value={emrText}
              onChange={(e) => setEmrText(e.target.value)}
              rows={10}
              className="w-full rounded border border-slate-300 px-2 py-1 text-sm font-mono"
            />
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-medium text-slate-700">
                Methods ({selectedIds.length}/8)
              </h2>
              <button
                type="button"
                onClick={() => setSelectedIds([])}
                className="text-xs text-slate-500 hover:text-slate-700"
              >
                clear
              </button>
            </div>
            {!methodsList && <div className="text-xs text-slate-400">loading methods…</div>}
            {Array.from(groupedByFamily.entries()).map(([family, methods]) => (
              <div key={family} className="mb-3">
                <div className="mb-1 text-xs font-semibold uppercase text-slate-500">
                  {family}
                </div>
                <div className="space-y-1">
                  {methods.map((m) => {
                    const checked = selectedIds.includes(m.method_id);
                    const disabled = !checked && selectedIds.length >= 8;
                    return (
                      <label
                        key={m.method_id}
                        className={`flex items-start gap-2 rounded px-2 py-1 text-xs ${
                          disabled
                            ? 'cursor-not-allowed opacity-50'
                            : 'cursor-pointer hover:bg-slate-50'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={disabled}
                          onChange={() => toggleMethod(m.method_id)}
                          className="mt-0.5"
                        />
                        <div className="flex-1">
                          <div className="flex items-center gap-1">
                            <span className="font-mono text-slate-700">{m.method_id}</span>
                            {!m.available && (
                              <span
                                className="rounded bg-amber-100 px-1 py-0.5 text-amber-700"
                                title="missing required capabilities"
                              >
                                unavail
                              </span>
                            )}
                          </div>
                          <div className="text-slate-500">{m.method_name}</div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
            {methodsList && (
              <div className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-500">
                Capabilities:&nbsp;
                {Object.entries(methodsList.capabilities).map(([k, v]) => (
                  <span
                    key={k}
                    className={`mr-2 rounded px-1 py-0.5 ${
                      v ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                    }`}
                  >
                    {k}={v ? '✓' : '✗'}
                  </span>
                ))}
              </div>
            )}
          </section>

          <button
            type="button"
            onClick={runCompare}
            disabled={loading || selectedIds.length === 0}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Running…
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Run Compare
              </>
            )}
          </button>
        </aside>

        {/* Right: results */}
        <main className="lg:col-span-8 space-y-4">
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
              <div>{error}</div>
            </div>
          )}

          {response && (
            <>
              <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                  <Stat label="Case ID" value={response.case_id || '—'} />
                  <Stat label="EMR Chars" value={String(response.emr_chars)} />
                  <Stat label="Methods Run" value={String(response.method_count)} />
                  <Stat
                    label="Consensus"
                    value={response.consensus_primary_code || '—'}
                    sub={
                      response.consensus_count > 0
                        ? `${response.consensus_count} method(s) agree`
                        : ''
                    }
                    highlight={response.consensus_count > 1}
                  />
                </div>
              </section>

              <MethodComparisonGrid
                results={response.results}
                consensusCode={response.consensus_primary_code}
              />
            </>
          )}

          {!response && !error && !loading && (
            <div className="rounded-lg border-2 border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
              <RefreshCw className="mx-auto mb-2 h-6 w-6 text-slate-300" />
              Configure methods on the left and click <strong>Run Compare</strong>.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div
        className={`mt-1 text-lg font-semibold ${
          highlight ? 'text-emerald-700' : 'text-slate-900'
        }`}
      >
        {value}
      </div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}