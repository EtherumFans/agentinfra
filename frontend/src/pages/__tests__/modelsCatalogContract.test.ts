import fs from 'fs';
import path from 'path';

import { describe, expect, it } from 'vitest';


const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const page = fs.readFileSync(path.join(ROOT, 'frontend/src/pages/ModelsPage.tsx'), 'utf-8');
const app = fs.readFileSync(path.join(ROOT, 'frontend/src/App.tsx'), 'utf-8');
const layout = fs.readFileSync(path.join(ROOT, 'frontend/src/components/layout/Layout.tsx'), 'utf-8');
const api = fs.readFileSync(path.join(ROOT, 'frontend/src/services/api.ts'), 'utf-8');


describe('iCoDer Models catalog contract', () => {
  it('has an authenticated Console route and navigation entry', () => {
    expect(app).toContain('path="models" element={<ModelsPage />}');
    expect(layout).toContain("to: '/models'");
  });

  it('loads the authoritative secret-free backend catalog', () => {
    expect(api).toContain("api.get('/v1/model-catalog')");
    expect(page).toContain('modelCatalogApi.get()');
    expect(page).not.toContain('ICODER_CREDENTIAL_LLM');
    expect(page).not.toContain('api_key');
  });

  it('supports owner/admin versioned tenant deployment selection', () => {
    expect(api).toContain("api.put('/v1/model-catalog/selection', data)");
    expect(page).toContain("updateSelection('pinned', deployment.id)");
    expect(page).toContain('expected_version: catalog.tenant_selection.version');
    expect(page).toContain('仅 owner/admin 可修改');
    expect(page).toContain('固定部署不可静默切换到全局 fallback');
  });

  it('does not present configuration as live provider health', () => {
    expect(page).toContain('configured_not_live_verified');
    expect(page).toContain('配置探针只证明配置');
    expect(page).toContain('实网 Canary 只证明一次固定合成载荷的连通性');
    expect(page).toContain('不证明临床质量、持续可用性');
  });

  it('exposes the owner/admin no-network configuration probe', () => {
    expect(api).toContain("api.post('/v1/model-catalog/health-probe'");
    expect(page).toContain('modelCatalogApi.healthProbe');
    expect(page).toContain('运行配置健康探针');
  });

  it('requires explicit confirmation for a fixed no-patient-data live canary', () => {
    expect(api).toContain("api.post('/v1/model-catalog/live-canary'");
    expect(api).toContain('acknowledge_external_call: true');
    expect(api).toContain("purpose: 'connectivity_only_no_patient_data'");
    expect(page).toContain('window.confirm');
    expect(page).toContain('固定、无患者数据的实网连通性请求');
    expect(page).toContain('该结果只证明一次连通性');
  });

  it('shows the metadata-only clinical package governance boundary', () => {
    expect(api).toContain("api.get('/v1/clinical-model-packages')");
    expect(api).toContain('acknowledge_clinical_governance: true');
    expect(page).toContain('modelCatalogApi.listClinicalPackages()');
    expect(page).toContain('模型二进制、训练病例、患者文本与凭据不进入控制面');
    expect(page).toContain('运行时模型装载：关闭');
  });

  it('exposes signed synthetic attestations while keeping shadow bindings out of Runtime', () => {
    expect(api).toContain('/synthetic-artifact-probe`');
    expect(api).toContain('/artifact-attestations`');
    expect(api).toContain('/shadow-bindings/${encodeURIComponent(useCase)}`');
    expect(api).toContain('acknowledge_shadow_only: true');
    expect(api).toContain('/synthetic-evaluation`');
    expect(api).toContain('/evaluations`');
    expect(api).toContain('acknowledge_synthetic_only: true');
    expect(page).toContain('自动回滚');
    expect(page).toContain('fencing token');
    expect(page).toContain('旧 worker 不能结算');
    expect(page).toContain('哈希与聚合计数');
    expect(page).toContain('不接收患者数据、不输出预测，也不接入生产 Runtime');
    expect(api).toContain('/evaluation-jobs`');
    expect(api).toContain("'Idempotency-Key': idempotencyKey");
    expect(api).toContain('/shadow-evaluation-jobs/${encodeURIComponent(jobId)}/execute`');
    expect(api).toContain('/shadow-evaluation-jobs/${encodeURIComponent(jobId)}/cancel`');
    expect(api).toContain('/shadow-evaluation-jobs/health/summary');
    expect(api).toContain('/shadow-evaluation-jobs/maintenance/run');
    expect(api).toContain('/shadow-evaluation-jobs/dead-letters/list');
    expect(api).toContain('/dead-letters/${encodeURIComponent(deadLetterId)}/replay`');
    expect(api).toContain('/shadow-evaluation-jobs/alerts/states');
    expect(page).toContain('modelCatalogApi.getClinicalShadowEvaluationJobHealth()');
    expect(page).toContain('Shadow 作业健康');
    expect(page).toContain('过期租约');
    expect(page).toContain('耗尽待维护');
    expect(page).toContain('待处理死信');
    expect(page).toContain('modelCatalogApi.listClinicalShadowAlertStates()');
  });
});
