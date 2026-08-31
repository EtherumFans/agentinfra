import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cloud,
  Cpu,
  Database,
  RefreshCw,
  Server,
  ShieldCheck,
} from 'lucide-react';

import { useLocaleStore } from '../i18n';
import { modelCatalogApi } from '../services/api';


type ModelStatus =
  | 'available_to_configure'
  | 'configured_not_live_verified'
  | 'development_only'
  | 'blocked';

interface ModelCatalogItem {
  id: string;
  display_name: string;
  model: string;
  deployment_kind: string;
  selected: boolean;
  credential_required: boolean;
  credential_configured: boolean | null;
  adapter_capabilities: string[];
  china_scenario: string;
  provider_region: string;
  tenant_region: string;
  egress_decision: 'allow' | 'deny';
  status: ModelStatus;
  blocking_reasons: string[];
  health_status?: string;
  health_checked_at?: string | null;
  canary_status?: string;
  canary_checked_at?: string | null;
  canary_scope?: 'connectivity_only_no_patient_data';
}

interface ModelCatalogResponse {
  active_provider: string;
  active_model: string;
  operator_default_provider: string;
  operator_default_model: string;
  effective_deployment_id: string;
  tenant_selection: {
    mode: 'inherit' | 'pinned';
    deployment_id: string | null;
    version: number;
  };
  registered_deployments: Array<{
    id: string;
    provider_id: string;
    model: string;
    is_default: boolean;
    tenant_selectable: boolean;
    credential_configured: boolean;
    canary_status?: string;
    canary_checked_at?: string | null;
  }>;
  selection_editable: boolean;
  live_canary_available: boolean;
  live_canary_policy: {
    purpose: 'connectivity_only_no_patient_data';
    fixed_synthetic_payload: true;
    patient_data_allowed: false;
    requires_owner_admin: true;
    requires_explicit_acknowledgement: true;
    max_cost_cny: number;
    max_output_tokens: number;
    timeout_seconds: number;
    cooldown_seconds: number;
  };
  tenant_region: string;
  egress_policy: string;
  external_llm_allowed: boolean;
  models: ModelCatalogItem[];
  readiness_scope: string;
  live_health_verified: boolean;
  disclaimer: string;
}

interface ClinicalModelPackage {
  id: string;
  package_key: string;
  package_version: string;
  use_case: string;
  model_kind: string;
  status: 'draft' | 'submitted' | 'approved' | 'active' | 'retired' | 'rejected';
  license_status: string;
  redistribution_authorized: boolean;
  cloud_use_authorized: boolean;
  hospital_use_authorized: boolean;
  independent_gold_validated: boolean;
  independent_reviewer_approved: boolean;
  binary_stored: false;
  patient_data_stored: false;
}

interface ClinicalModelPackageList {
  items: ClinicalModelPackage[];
  count: number;
  governance_scope: 'metadata_and_evidence_digests_only';
  runtime_loading_enabled: false;
}

interface ClinicalModelShadowJobHealth {
  status: 'healthy' | 'degraded';
  status_counts: Record<string, number>;
  due_queued_count: number;
  active_lease_count: number;
  expired_lease_count: number;
  exhausted_count: number;
  dead_letter_count: number;
  oldest_due_age_seconds: number;
  alert_codes: string[];
  aggregate_only: true;
  patient_data_used: false;
  identifiers_emitted: false;
}

interface ClinicalModelShadowAlertStateList {
  items: Array<{
    alert_code: string;
    state: 'firing' | 'resolved';
    occurrence_count: number;
  }>;
  count: number;
  aggregate_only: true;
  patient_data_used: false;
  identifiers_emitted: false;
}


const statusClasses: Record<ModelStatus, string> = {
  available_to_configure: 'bg-muted text-muted-foreground',
  configured_not_live_verified: 'bg-amber-100 text-amber-800',
  development_only: 'bg-sky-100 text-sky-800',
  blocked: 'bg-red-100 text-red-700',
};


export default function ModelsPage() {
  const locale = useLocaleStore((state) => state.locale);
  const zh = locale === 'zh-CN';
  const [catalog, setCatalog] = useState<ModelCatalogResponse | null>(null);
  const [clinicalPackages, setClinicalPackages] = useState<ClinicalModelPackageList | null>(null);
  const [shadowJobHealth, setShadowJobHealth] = useState<ClinicalModelShadowJobHealth | null>(null);
  const [shadowAlertStates, setShadowAlertStates] = useState<ClinicalModelShadowAlertStateList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [savingSelection, setSavingSelection] = useState('');
  const [probingHealth, setProbingHealth] = useState(false);
  const [runningCanary, setRunningCanary] = useState(false);
  const [canaryNotice, setCanaryNotice] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [catalogResponse, packagesResponse, shadowHealthResponse, shadowAlertsResponse] = await Promise.all([
        modelCatalogApi.get(),
        modelCatalogApi.listClinicalPackages(),
        modelCatalogApi.getClinicalShadowEvaluationJobHealth(),
        modelCatalogApi.listClinicalShadowAlertStates(),
      ]);
      setCatalog(catalogResponse.data as ModelCatalogResponse);
      setClinicalPackages(packagesResponse.data as ClinicalModelPackageList);
      setShadowJobHealth(shadowHealthResponse.data as ClinicalModelShadowJobHealth);
      setShadowAlertStates(shadowAlertsResponse.data as ClinicalModelShadowAlertStateList);
    } catch {
      setError(zh ? '无法读取模型目录。' : 'Unable to load the model catalog.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const updateSelection = async (mode: 'inherit' | 'pinned', deploymentId = '') => {
    if (!catalog) return;
    setSavingSelection(deploymentId || 'inherit');
    setError('');
    try {
      await modelCatalogApi.updateSelection({
        mode,
        ...(deploymentId ? { deployment_id: deploymentId } : {}),
        expected_version: catalog.tenant_selection.version,
      });
      await load();
    } catch {
      setError(zh
        ? '模型选择未保存：配置可能已被其他管理员更新，或该部署不再可用。'
        : 'Model selection was not saved: it may have changed or the deployment is unavailable.');
    } finally {
      setSavingSelection('');
    }
  };

  const probeHealth = async () => {
    if (!catalog?.effective_deployment_id || !catalog.selection_editable) return;
    setProbingHealth(true);
    setError('');
    try {
      await modelCatalogApi.healthProbe(catalog.effective_deployment_id);
      await load();
    } catch {
      setError(zh
        ? '配置健康探针失败；未发起模型请求，请检查部署目录和权限。'
        : 'Configuration health probe failed; no model request was sent. Check deployment and permissions.');
    } finally {
      setProbingHealth(false);
    }
  };

  const runLiveCanary = async () => {
    if (!catalog?.effective_deployment_id || !catalog.live_canary_available) return;
    const policy = catalog.live_canary_policy;
    const approved = window.confirm(zh
      ? `将向 ${catalog.effective_deployment_id} 发起一次固定、无患者数据的实网连通性请求；不会接受自由文本，费用上限 ¥${policy.max_cost_cny.toFixed(4)}，${policy.cooldown_seconds} 秒内不可重复。确认执行？`
      : `Send one fixed no-patient-data connectivity request to ${catalog.effective_deployment_id}. No free text is accepted; cost cap ¥${policy.max_cost_cny.toFixed(4)} and cooldown ${policy.cooldown_seconds}s. Continue?`);
    if (!approved) return;
    setRunningCanary(true);
    setError('');
    setCanaryNotice('');
    try {
      const response = await modelCatalogApi.liveCanary(
        catalog.effective_deployment_id,
        policy.max_cost_cny,
      );
      const result = response.data as {
        status: string;
        latency_ms: number;
        cost: { amount: number };
      };
      setCanaryNotice(zh
        ? `实网 Canary：${result.status}，${result.latency_ms} ms，费用估算 ¥${result.cost.amount.toFixed(6)}。该结果只证明一次连通性。`
        : `Live canary: ${result.status}, ${result.latency_ms} ms, estimated cost ¥${result.cost.amount.toFixed(6)}. This proves one connectivity observation only.`);
      await load();
    } catch {
      setError(zh
        ? '实网 Canary 未执行或失败：请检查显式开关、owner/admin 权限、外发策略、预算和冷却时间。'
        : 'Live canary was not run or failed. Check the explicit switch, owner/admin role, egress policy, budget and cooldown.');
    } finally {
      setRunningCanary(false);
    }
  };

  const active = useMemo(
    () => catalog?.models.find((item) => item.selected) ?? null,
    [catalog],
  );

  const statusLabel = (status: ModelStatus) => {
    const labels: Record<ModelStatus, [string, string]> = {
      available_to_configure: ['可配置', 'Available to configure'],
      configured_not_live_verified: ['已配置，未实网验证', 'Configured, not live verified'],
      development_only: ['仅开发测试', 'Development only'],
      blocked: ['已阻断', 'Blocked'],
    };
    return labels[status][zh ? 0 : 1];
  };

  return (
    <div className="flex-1 overflow-y-auto bg-muted/20">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
              <Cpu size={16} /> iCoDer Models
            </div>
            <h1 className="text-2xl font-semibold text-foreground">
              {zh ? '医疗模型与数据外发门禁' : 'Clinical models and egress controls'}
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              {zh
                ? '展示当前运行时真正选择的模型、适配器合同、区域策略与阻断原因。页面不会返回密钥或完整模型端点，也不会把“已配置”冒充为“已验证可用”。'
                : 'Shows the actual runtime selection, adapter contract, region policy and blockers. Secrets and full endpoints are never returned, and configuration is not presented as live health.'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm hover:bg-accent disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            {zh ? '刷新' : 'Refresh'}
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <AlertTriangle size={17} /> {error}
          </div>
        )}

        {canaryNotice && (
          <div className="flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-800">
            <ShieldCheck size={17} /> {canaryNotice}
          </div>
        )}

        {loading && !catalog ? (
          <div className="rounded-xl border border-border bg-background p-8 text-center text-sm text-muted-foreground">
            {zh ? '正在读取运行时配置…' : 'Loading runtime configuration…'}
          </div>
        ) : catalog && (
          <>
            <div className="grid gap-4 md:grid-cols-4">
              <SummaryCard icon={Cpu} label={zh ? '当前 Provider' : 'Active provider'} value={catalog.active_provider} />
              <SummaryCard icon={Database} label={zh ? '当前模型' : 'Active model'} value={catalog.active_model || '—'} />
              <SummaryCard icon={ShieldCheck} label={zh ? '外发策略' : 'Egress policy'} value={`${catalog.tenant_region.toUpperCase()} / ${catalog.egress_policy}`} />
              <SummaryCard
                icon={Cloud}
                label={zh ? '外部 LLM' : 'External LLM'}
                value={catalog.external_llm_allowed ? (zh ? '允许' : 'Allowed') : (zh ? '禁止' : 'Denied')}
              />
            </div>

            <div className="rounded-xl border border-border bg-background p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="font-medium text-foreground">
                    {zh ? '租户模型路由' : 'Tenant model routing'}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {zh
                      ? `当前为${catalog.tenant_selection.mode === 'pinned' ? '固定部署' : '继承运维默认'}；选择版本 ${catalog.tenant_selection.version}。`
                      : `${catalog.tenant_selection.mode === 'pinned' ? 'Pinned deployment' : 'Inheriting operator default'}; selection version ${catalog.tenant_selection.version}.`}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {zh
                      ? `运维默认：${catalog.operator_default_provider} / ${catalog.operator_default_model}`
                      : `Operator default: ${catalog.operator_default_provider} / ${catalog.operator_default_model}`}
                  </p>
                </div>
                {!catalog.selection_editable && (
                  <span className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                    {zh ? '仅 owner/admin 可修改' : 'Owner/admin only'}
                  </span>
                )}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={!catalog.selection_editable || Boolean(savingSelection) || catalog.tenant_selection.mode === 'inherit'}
                  onClick={() => void updateSelection('inherit')}
                  className="rounded-md border border-border px-3 py-2 text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {savingSelection === 'inherit' ? (zh ? '保存中…' : 'Saving…') : (zh ? '继承运维默认' : 'Inherit operator default')}
                </button>
                {catalog.registered_deployments
                  .filter((deployment) => deployment.tenant_selectable)
                  .map((deployment) => {
                    const selected = catalog.tenant_selection.mode === 'pinned'
                      && catalog.tenant_selection.deployment_id === deployment.id;
                    return (
                      <button
                        key={deployment.id}
                        type="button"
                        disabled={!catalog.selection_editable || Boolean(savingSelection) || selected}
                        onClick={() => void updateSelection('pinned', deployment.id)}
                        className={`rounded-md border px-3 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-50 ${selected ? 'border-primary bg-primary/5' : 'border-border hover:bg-accent'}`}
                      >
                        <span className="font-medium">{deployment.id}</span>
                        <span className="ml-2 text-xs text-muted-foreground">{deployment.provider_id} / {deployment.model} · Canary {deployment.canary_status || 'not_run'}</span>
                      </button>
                    );
                  })}
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                {zh
                  ? '固定部署不可静默切换到全局 fallback；部署下线或策略拒绝时请求失败关闭。'
                  : 'Pinned deployments never silently switch to the global fallback; removed or denied deployments fail closed.'}
              </p>
            </div>

            {active && (
              <div className={`rounded-xl border p-5 ${active.status === 'blocked' ? 'border-red-200 bg-red-50/60' : 'border-amber-200 bg-amber-50/50'}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    {active.status === 'blocked' ? <AlertTriangle className="text-red-600" /> : <CheckCircle2 className="text-amber-600" />}
                    <div>
                      <p className="font-medium text-foreground">{active.display_name} · {active.model}</p>
                      <p className="text-xs text-muted-foreground">
                        {zh ? '当前运行时选择' : 'Current runtime selection'} · {statusLabel(active.status)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground">
                      {zh ? `配置探针：${active.health_status || '未运行'}` : `Config probe: ${active.health_status || 'not run'}`}
                    </span>
                    <span className="rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground">
                      {zh ? `实网 Canary：${active.canary_status || '未运行'}` : `Live canary: ${active.canary_status || 'not run'}`}
                    </span>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClasses[active.status]}`}>
                      {statusLabel(active.status)}
                    </span>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void probeHealth()}
                    disabled={!catalog.selection_editable || probingHealth}
                    className="rounded-md border border-border px-3 py-2 text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {probingHealth ? (zh ? '探测中…' : 'Probing…') : (zh ? '运行配置健康探针' : 'Run configuration probe')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void runLiveCanary()}
                    disabled={!catalog.live_canary_available || runningCanary}
                    className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {runningCanary
                      ? (zh ? '实网请求中…' : 'Running live request…')
                      : (zh ? '运行一次实网 Canary' : 'Run one live canary')}
                  </button>
                  {active.health_checked_at && (
                    <span className="text-xs text-muted-foreground">
                      {zh ? `最近检查：${new Date(active.health_checked_at).toLocaleString()}` : `Checked: ${new Date(active.health_checked_at).toLocaleString()}`}
                    </span>
                  )}
                  {active.canary_checked_at && (
                    <span className="text-xs text-muted-foreground">
                      {zh ? `Canary：${new Date(active.canary_checked_at).toLocaleString()}` : `Canary: ${new Date(active.canary_checked_at).toLocaleString()}`}
                    </span>
                  )}
                </div>
                {active.blocking_reasons.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {active.blocking_reasons.map((reason) => (
                      <code key={reason} className="rounded bg-background px-2 py-1 text-xs text-red-700">{reason}</code>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              {catalog.models.map((item) => (
                <div key={item.id} className={`rounded-xl border bg-background p-5 ${item.selected ? 'border-primary/50 ring-1 ring-primary/20' : 'border-border'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <div className="rounded-lg border border-border bg-muted/30 p-2">
                        {item.deployment_kind === 'self_hosted' ? <Server size={18} /> : <Cloud size={18} />}
                      </div>
                      <div>
                        <h2 className="font-medium text-foreground">{item.display_name}</h2>
                        <p className="mt-1 font-mono text-xs text-muted-foreground">{item.model}</p>
                      </div>
                    </div>
                    <span className={`rounded-full px-2 py-1 text-[11px] font-medium ${statusClasses[item.status]}`}>
                      {statusLabel(item.status)}
                    </span>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-muted-foreground">{item.china_scenario}</p>
                  <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                    <KeyValue label={zh ? 'Provider 区域' : 'Provider region'} value={item.provider_region.toUpperCase()} />
                    <KeyValue label={zh ? '外发判定' : 'Egress decision'} value={item.egress_decision} danger={item.egress_decision === 'deny'} />
                    <KeyValue label={zh ? '需要凭证' : 'Credential required'} value={item.credential_required ? (zh ? '是' : 'Yes') : (zh ? '否' : 'No')} />
                    <KeyValue
                      label={zh ? '凭证状态' : 'Credential state'}
                      value={item.credential_configured === null ? (zh ? '选择后评估' : 'Evaluated when selected') : item.credential_configured ? (zh ? '已提供' : 'Present') : (zh ? '未提供' : 'Missing')}
                    />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {item.adapter_capabilities.map((capability) => (
                      <span key={capability} className="rounded bg-muted px-2 py-1 text-[11px] text-muted-foreground">{capability}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-border bg-background p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-medium text-foreground">
                    {zh ? '临床模型包治理' : 'Clinical model package governance'}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {zh
                      ? '这里只展示不可变版本和证据摘要；模型二进制、训练病例、患者文本与凭据不进入控制面。提交、四眼审批、激活和回滚均通过 owner/admin API 或 SDK 完成。'
                      : 'Only immutable versions and evidence digests are represented. Model binaries, training rows, patient text and credentials never enter this control plane. Submission, four-eyes approval, activation and rollback use the owner/admin API or SDK.'}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {zh
                      ? '开发环境可将签名合成包的三轮隔离 observation 放入带幂等键和 fencing token 的异步作业；受控故障停止并自动回滚，worker 崩溃后租约到期可恢复，旧 worker 不能结算，耗尽尝试会释放活动槽位。门禁仍只保存哈希与聚合计数；不接收患者数据、不输出预测，也不接入生产 Runtime。'
                      : 'Development can queue three isolated observations of signed synthetic bundles as idempotent jobs with fenced leases. Controlled faults stop and automatically roll back; expired work can be recovered after worker failure, stale workers cannot settle, and exhausted attempts release the active slot. The gate still stores hashes and aggregate counts only, with no patient data, predictions, or production Runtime routing.'}
                  </p>
                  {shadowJobHealth && (
                    <div className="mt-3 flex flex-wrap gap-2 text-xs">
                      <span className={`rounded px-2 py-1 ${shadowJobHealth.status === 'healthy' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-700'}`}>
                        {zh ? 'Shadow 作业健康' : 'Shadow job health'}: {shadowJobHealth.status}
                      </span>
                      <span className="rounded bg-muted px-2 py-1 text-muted-foreground">
                        {zh ? '到期排队' : 'Due queued'}: {shadowJobHealth.due_queued_count}
                      </span>
                      <span className="rounded bg-muted px-2 py-1 text-muted-foreground">
                        {zh ? '活动租约' : 'Active leases'}: {shadowJobHealth.active_lease_count}
                      </span>
                      <span className="rounded bg-muted px-2 py-1 text-muted-foreground">
                        {zh ? '过期租约' : 'Expired leases'}: {shadowJobHealth.expired_lease_count}
                      </span>
                      <span className="rounded bg-muted px-2 py-1 text-muted-foreground">
                        {zh ? '耗尽待维护' : 'Exhausted'}: {shadowJobHealth.exhausted_count}
                      </span>
                      <span className="rounded bg-muted px-2 py-1 text-muted-foreground">
                        {zh ? '待处理死信' : 'Dead letters'}: {shadowJobHealth.dead_letter_count}
                      </span>
                      {shadowJobHealth.alert_codes.map((code) => (
                        <code key={code} className="rounded bg-red-50 px-2 py-1 text-red-700">{code}</code>
                      ))}
                    </div>
                  )}
                  {shadowAlertStates && shadowAlertStates.count > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      {shadowAlertStates.items.map((item) => (
                        <span
                          key={item.alert_code}
                          className={`rounded px-2 py-1 ${item.state === 'firing' ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-800'}`}
                        >
                          {item.alert_code}: {item.state} · {item.occurrence_count}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <span className="rounded bg-amber-100 px-2 py-1 text-xs text-amber-800">
                  {zh ? '运行时模型装载：关闭' : 'Runtime model loading: disabled'}
                </span>
              </div>
              {!clinicalPackages || clinicalPackages.count === 0 ? (
                <p className="mt-4 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                  {zh ? '本组织尚未登记临床模型包。' : 'No clinical model package is registered for this organization.'}
                </p>
              ) : (
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  {clinicalPackages.items.map((item) => {
                    const gates = [
                      ['license', item.license_status === 'verified'],
                      ['redistribution', item.redistribution_authorized],
                      ['hospital', item.hospital_use_authorized],
                      ['cloud', item.cloud_use_authorized],
                      ['independent gold', item.independent_gold_validated],
                      ['independent reviewer', item.independent_reviewer_approved],
                    ] as const;
                    return (
                      <div key={item.id} className="rounded-lg border border-border p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-foreground">
                              {item.package_key} · {item.package_version}
                            </p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {item.use_case} / {item.model_kind}
                            </p>
                          </div>
                          <span className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                            {item.status}
                          </span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {gates.map(([label, passed]) => (
                            <span
                              key={label}
                              className={`rounded px-2 py-1 text-[11px] ${passed ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-700'}`}
                            >
                              {label}: {passed ? 'pass' : 'blocked'}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-border bg-background p-5 text-sm text-muted-foreground">
              <div className="flex items-start gap-3">
                <ShieldCheck size={18} className="mt-0.5 shrink-0 text-primary" />
                <div>
                  <p className="font-medium text-foreground">
                    {zh ? '证据边界' : 'Evidence boundary'}
                  </p>
                  <p className="mt-1 leading-6">
                    {zh
                      ? '配置探针只证明配置；实网 Canary 只证明一次固定合成载荷的连通性。两者都不证明临床质量、持续可用性、账单准确性、数据处理协议或医院准入。'
                      : catalog.disclaimer}
                  </p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}


function SummaryCard({ icon: Icon, label, value }: { icon: typeof Cpu; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground"><Icon size={14} /> {label}</div>
      <p className="mt-2 truncate font-medium text-foreground" title={value}>{value}</p>
    </div>
  );
}


function KeyValue({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className={`mt-1 font-medium ${danger ? 'text-red-600' : 'text-foreground'}`}>{value}</p>
    </div>
  );
}
