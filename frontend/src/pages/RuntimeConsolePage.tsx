/** RuntimeConsolePage — PlatformRuntime status, observability, agent management. */

import { useEffect, useState } from 'react';
import { runtimeApi } from '../services/runtimeApi';
import type {
  RuntimeStatus, DataPolicy, RegistryHealth, FallbackStats, ShadowStats,
  InstalledAgent, MedicalCodingStatus, RuleEngineStatus,
} from '../types/runtime';

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, minWidth: 160 }}>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 600 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 8, color: '#1f2937' }}>{title}</h3>
      {children}
    </div>
  );
}

export default function RuntimeConsolePage() {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [policy, setPolicy] = useState<DataPolicy | null>(null);
  const [health, setHealth] = useState<RegistryHealth | null>(null);
  const [fallback, setFallback] = useState<FallbackStats | null>(null);
  const [shadow, setShadow] = useState<ShadowStats | null>(null);
  const [agents, setAgents] = useState<InstalledAgent[]>([]);
  const [mcStatus, setMcStatus] = useState<MedicalCodingStatus | null>(null);
  const [reStatus, setReStatus] = useState<RuleEngineStatus | null>(null);
  const [runs, setRuns] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const [s, p, h, f, sh, a, mc, re, r] = await Promise.all([
          runtimeApi.getStatus().catch(() => null),
          runtimeApi.getDataPolicy().catch(() => null),
          runtimeApi.getRegistryHealth().catch(() => null),
          runtimeApi.getFallbackStats().catch(() => null),
          runtimeApi.getShadowStats().catch(() => null),
          runtimeApi.listAgents().catch(() => ({ agents: [] })),
          runtimeApi.getMedicalCodingStatus().catch(() => null),
          runtimeApi.getRuleEngineStatus().catch(() => null),
          runtimeApi.listRuns('', 10).catch(() => ({ runs: [] })),
        ]);
        setStatus(s); setPolicy(p); setHealth(h); setFallback(f); setShadow(sh);
        setAgents(a?.agents || []); setMcStatus(mc); setReStatus(re);
        setRuns(r?.runs || []);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load Runtime Console');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div style={{ padding: 24 }}>Loading Runtime Console...</div>;
  if (error) return <div style={{ padding: 24, color: '#dc2626' }}>Error: {error}</div>;

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Runtime Console</h2>

      {/* Status Cards */}
      <Section title="PlatformRuntime Status">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <StatCard label="Started" value={status?.started ? 'Yes' : 'No'} sub={status?.started_at?.slice(0, 19)} />
          <StatCard label="Execution Mode" value={status?.execution_mode || '—'} />
          <StatCard label="Review Coding Mode" value={status?.review_coding_mode || '—'} />
          <StatCard label="Fallback to Legacy" value={status?.fallback_to_legacy ? 'Yes' : 'No'} />
          <StatCard label="Installed Agents" value={status?.agents_installed ?? '—'} />
          <StatCard label="Default Provider" value={status?.default_provider || '—'} />
        </div>
      </Section>

      {/* Data Policy */}
      <Section title="Data Policy">
        {policy ? (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <StatCard label="External LLM" value={policy.allow_external_llm ? 'Allowed' : 'Blocked'}
              sub={policy.allow_external_llm ? '' : 'Hospital internal mode'} />
            <StatCard label="PII Redaction" value={policy.pii_redaction_required ? 'On' : 'Off'} />
            <StatCard label="Persist Full Input" value={policy.persist_full_input ? 'Yes' : 'No'} />
            <StatCard label="Marketplace Sync" value={policy.marketplace_sync_mode} />
            <StatCard label="Audit Log Local Only" value={policy.audit_log_local_only ? 'Yes' : 'No'} />
          </div>
        ) : <div style={{ color: '#9ca3af' }}>Data Policy not available</div>}
      </Section>

      {/* Registry */}
      <Section title="Registry Health">
        {health ? (
          <>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <StatCard label="Healthy" value={health.healthy ? 'Yes' : 'No'} />
              <StatCard label="Registry Agents" value={health.total_registry} />
              <StatCard label="DB Agents" value={health.total_db} />
              <StatCard label="Inconsistencies" value={health.inconsistency_count}
                sub={health.inconsistency_count > 0 ? 'Needs repair' : 'Clean'} />
              <StatCard label="Schema Version" value={health.schema_version} />
              <StatCard label="Path" value={health.registry_path?.split('/').pop() || '—'} />
            </div>
            {health.inconsistency_count > 0 && (
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <button
                  onClick={async () => {
                    try {
                      const data = await runtimeApi.getRegistryInconsistencies();
                      alert(JSON.stringify(data, null, 2));
                    } catch { alert('Failed to load inconsistencies'); }
                  }}
                  style={{ fontSize: 12, padding: '4px 12px', borderRadius: 4, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}
                >
                  查看不一致详情
                </button>
                <button
                  onClick={async () => {
                    if (!confirm('确定要用 Registry 修复 DB？Registry 是权威数据源。')) return;
                    try {
                      const result = await runtimeApi.repairRegistry('registry_to_db');
                      alert(`修复完成: ${JSON.stringify(result)}`);
                      const h = await runtimeApi.getRegistryHealth();
                      setHealth(h);
                    } catch { alert('修复失败，请检查权限'); }
                  }}
                  style={{ fontSize: 12, padding: '4px 12px', borderRadius: 4, border: '1px solid #f59e0b', background: '#fef3c7', color: '#92400e', cursor: 'pointer' }}
                >
                  一键修复 (Registry → DB)
                </button>
              </div>
            )}
          </>
        ) : <div style={{ color: '#9ca3af' }}>Registry health requires admin authentication</div>}
      </Section>

      {/* Providers */}
      <Section title="LLM Providers">
        {status?.providers ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(status.providers).map(([name, info]) => (
              <div key={name} style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6, padding: '8px 12px', fontSize: 12 }}>
                <strong>{name}</strong>: {typeof info === 'object' ? String((info as Record<string, string>).status || 'unknown') : String(info)}
                {(info as Record<string, string>).mode ? <> · mode: {(info as Record<string, string>).mode}</> : null}
              </div>
            ))}
          </div>
        ) : <div style={{ color: '#9ca3af' }}>No provider info</div>}
      </Section>

      {/* Medical Coding */}
      <Section title="Medical Coding Agent">
        {mcStatus ? (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <StatCard label="Mode" value={mcStatus.mode} />
            <StatCard label="Model" value={mcStatus.model} />
            <StatCard label="External LLM" value={mcStatus.external_llm_allowed ? 'Allowed' : 'Blocked'} />
            <StatCard label="PII Redaction" value={mcStatus.pii_redaction_enabled ? 'On' : 'Off'} />
          </div>
        ) : <div style={{ color: '#9ca3af' }}>Not available</div>}
      </Section>

      {/* Rule Engine */}
      <Section title="Rule Engine">
        {reStatus ? (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <StatCard label="Status" value={reStatus.status} />
            <StatCard label="Rule Sets" value={reStatus.total_rule_sets} sub={reStatus.loaded_rule_sets?.join(', ')} />
          </div>
        ) : <div style={{ color: '#9ca3af' }}>Not available</div>}
      </Section>

      {/* Observability */}
      <Section title="Observability">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {fallback?.available !== false ? (
            <>
              <StatCard label="Fallbacks (24h)" value={fallback?.total_fallbacks ?? '—'}
                sub={fallback?.fallback_rate ? `Rate: ${(fallback.fallback_rate * 100).toFixed(1)}%` : ''} />
              <StatCard label="Last Fallback" value={fallback?.last_fallback_at?.slice(0, 19) || 'None'} />
            </>
          ) : <div style={{ color: '#9ca3af' }}>Fallback not available</div>}
          {shadow?.available !== false ? (
            <>
              <StatCard label="Shadow Comparisons" value={shadow?.total_comparisons ?? '—'} />
              <StatCard label="Diagnosis Match" value={shadow?.diagnosis_match_rate ? `${(shadow.diagnosis_match_rate * 100).toFixed(1)}%` : '—'} />
              <StatCard label="Conclusion Match" value={shadow?.conclusion_match_rate ? `${(shadow.conclusion_match_rate * 100).toFixed(1)}%` : '—'} />
            </>
          ) : <div style={{ color: '#9ca3af' }}>Shadow not available</div>}
        </div>
      </Section>

      {/* Installed Agents */}
      <Section title={`Installed Agents (${agents.length})`}>
        {agents.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
                <th style={{ padding: '6px 8px' }}>Agent Ref</th>
                <th style={{ padding: '6px 8px' }}>Version</th>
                <th style={{ padding: '6px 8px' }}>Type</th>
                <th style={{ padding: '6px 8px' }}>Status</th>
                <th style={{ padding: '6px 8px' }}>Publisher</th>
                <th style={{ padding: '6px 8px' }}>Installed</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.agent_ref} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 12 }}>{a.agent_ref}</td>
                  <td style={{ padding: '6px 8px' }}>{a.version}</td>
                  <td style={{ padding: '6px 8px' }}>{a.agent_type}</td>
                  <td style={{ padding: '6px 8px', color: a.status === 'enabled' ? '#16a34a' : a.status === 'disabled' ? '#dc2626' : '#6b7280' }}>{a.status}</td>
                  <td style={{ padding: '6px 8px' }}>{a.publisher_name || '—'}</td>
                  <td style={{ padding: '6px 8px', fontSize: 11, color: '#6b7280' }}>{a.installed_at?.slice(0, 16) || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={{ color: '#9ca3af' }}>No agents installed in Runtime</div>}
      </Section>

      {/* Recent Runs */}
      <Section title={`Recent Runs (${runs.length})`}>
        {runs.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
                <th style={{ padding: '4px 6px' }}>Run ID</th>
                <th style={{ padding: '4px 6px' }}>Agent Ref</th>
                <th style={{ padding: '4px 6px' }}>Status</th>
                <th style={{ padding: '4px 6px' }}>Primary Dx</th>
                <th style={{ padding: '4px 6px' }}>Time (ms)</th>
                <th style={{ padding: '4px 6px' }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '4px 6px', fontFamily: 'monospace' }}>{(r as Record<string, unknown>).run_id as string}</td>
                  <td style={{ padding: '4px 6px', fontFamily: 'monospace', fontSize: 11 }}>{(r as Record<string, unknown>).agent_ref as string}</td>
                  <td style={{ padding: '4px 6px' }}>{(r as Record<string, unknown>).status as string}</td>
                  <td style={{ padding: '4px 6px' }}>{(r as Record<string, unknown>).primary_diagnosis_code as string || '—'}</td>
                  <td style={{ padding: '4px 6px' }}>{(r as Record<string, unknown>).processing_time_ms as number}</td>
                  <td style={{ padding: '4px 6px', fontSize: 11, color: '#6b7280' }}>{((r as Record<string, unknown>).timestamp as string)?.slice(0, 19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={{ color: '#9ca3af' }}>No runs recorded</div>}
      </Section>
    </div>
  );
}
