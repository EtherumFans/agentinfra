/**
 * cdiLabels — Phase 5 Track D P0.5 Gate 6 product-language maps.
 *
 * Maps raw backend enums / rule IDs to Chinese business labels suitable
 * for clinician / CDI specialist / auditor UI. Per Master Task §7.1-§7.3:
 *
 *   - 普通业务界面不得显示原始英文 enum / NLQ-001 等规则编号 / Token /
 *     run_id / trace_id / Raw Runtime Mode / 技术实现说明.
 *   - DRAFT → 草稿, PENDING_CDI_REVIEW → 待 CDI 审核, etc.
 *   - Gap Type / Case State / NLQ Verdict / Necessity Verdict 也必须中文化.
 *
 * Labels are tuned for Chinese hospital CDI workflow. Each map is a
 * Record<EnumValue, ChineseLabel>. Lookup helpers fall back to the
 * raw value when an unknown enum appears (forward-compatibility).
 */

import type {
  LifecycleState,
  NLQVerdict,
} from './cdiApi';

// ---------------------------------------------------------------------------
// Query lifecycle (12 states) — Master Task §7.2
// ---------------------------------------------------------------------------

export const LIFECYCLE_LABELS: Record<LifecycleState, string> = {
  DRAFT: '草稿',
  PENDING_CDI_REVIEW: '待 CDI 审核',
  APPROVED: '已批准',
  SENT_TO_CLINICIAN: '已发送医生',
  VIEWED: '医生已查看',
  RESPONDED: '医生已答复',
  DOCUMENTATION_UPDATED: '病历已更新',
  REVALIDATED: '已重新验证',
  CLOSED: '已关闭',
  CANCELLED: '已取消',
  ESCALATED: '已升级处理',
  EXPIRED: '已超期',
};

export function labelLifecycle(state: LifecycleState | string | undefined): string {
  if (!state) return '—';
  return LIFECYCLE_LABELS[state as LifecycleState] ?? state;
}

// ---------------------------------------------------------------------------
// Case completion state (4 states)
// ---------------------------------------------------------------------------

export const COMPLETION_LABELS: Record<string, string> = {
  AUTO_PASS: '自动通过',
  REVIEW_RECOMMENDED: '建议人工复核',
  REVIEW_REQUIRED: '需要人工审核',
  BLOCKED: '已阻断',
};

export function labelCompletion(state: string | undefined): string {
  if (!state) return '—';
  return COMPLETION_LABELS[state] ?? state;
}

// ---------------------------------------------------------------------------
// Gap type (9 types) — PDF §6.2
// ---------------------------------------------------------------------------

export const GAP_TYPE_LABELS: Record<string, string> = {
  diagnostic_specificity: '诊断特异性',
  etiology_unspecified: '病因未明确',
  severity_unspecified: '严重程度未明确',
  acuity_unspecified: '急慢性未区分',
  anatomical_site_unspecified: '解剖部位未明确',
  clinical_correlation_unestablished: '临床关联未建立',
  temporal_unspecified: '时间关系未明确',
  conflicting_documentation: '文档前后不一致',
  unknown: '未分类',
};

export function labelGapType(t: string | undefined): string {
  if (!t) return '—';
  return GAP_TYPE_LABELS[t] ?? t;
}

// ---------------------------------------------------------------------------
// NLQ verdict — Non-leading Query Gate
// ---------------------------------------------------------------------------

export const NLQ_VERDICT_LABELS: Record<NLQVerdict, string> = {
  PASS: '通过',
  BLOCK: '阻断',
  PENDING: '待校验',
};

export function labelNLQVerdict(v: NLQVerdict | string | undefined): string {
  if (!v) return '—';
  return NLQ_VERDICT_LABELS[v as NLQVerdict] ?? v;
}

// ---------------------------------------------------------------------------
// Specialist Trace — Expert IDs and execution modes (Gate 5)
// ---------------------------------------------------------------------------

export const EXPERT_LABELS: Record<string, string> = {
  'coding-expert': '编码专家',
  'pubmed-expert': '文献专家 (PubMed)',
  'web-search-expert': '指南检索专家',
  'medical-calculator-expert': '医学评分专家',
};

export function labelExpert(id: string | undefined): string {
  if (!id) return '—';
  return EXPERT_LABELS[id] ?? id;
}

export const EXECUTION_MODE_LABELS: Record<string, string> = {
  REAL_TOOL: '真实工具调用',
  LLM_KNOWLEDGE_ONLY: '模型知识 (未接真实工具)',
  SKIPPED_NOT_NEEDED: '未调用: 当前病例不需要',
  SKIPPED_MISSING_INPUTS: '未调用: 病历缺少必要参数',
  TOOL_UNAVAILABLE: '未调用: 暂未接入真实工具',
  DEGRADED: '调用失败 (降级)',
};

export function labelExecutionMode(m: string | undefined): string {
  if (!m) return '—';
  return EXECUTION_MODE_LABELS[m] ?? m;
}

// ---------------------------------------------------------------------------
// Risk flag category
// ---------------------------------------------------------------------------

export const RISK_FLAG_LABELS: Record<string, string> = {
  contradiction: '前后矛盾',
  unsupported_diagnosis: '诊断缺乏依据',
  ambiguous_term: '术语含糊',
  copied_forward_indicator: '复制粘贴迹象',
};

export function labelRiskCategory(c: string | undefined): string {
  if (!c) return c ?? '—';
  return RISK_FLAG_LABELS[c] ?? c;
}

// ---------------------------------------------------------------------------
// App role → Chinese label (workbench-local role display)
// ---------------------------------------------------------------------------

export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  cdi_specialist: 'CDI 专员',
  clinician: '临床医生',
  auditor: '审计员',
  read_only: '只读',
};

export function labelRole(r: string | undefined): string {
  if (!r) return '只读';
  return ROLE_LABELS[r] ?? r;
}

// ---------------------------------------------------------------------------
// Rule ID → human-readable description (for audit / specialist panels)
// ---------------------------------------------------------------------------

export const RULE_ID_LABELS: Record<string, string> = {
  // NLQ-001..011 (Non-leading Query Gate)
  'NLQ-001': '非诱导: 是非问句检测',
  'NLQ-002': '非诱导: 引导性动词检测',
  'NLQ-003': '非诱导: 引导性副词检测',
  'NLQ-004': '回答选项下限 (≥3)',
  'NLQ-005': '兜底选项存在 (无法确定 等)',
  'NLQ-006': '回应选项格式',
  'NLQ-007': '语言一致性',
  'NLQ-008': '证据引用',
  'NLQ-009': '问句主题清晰',
  'NLQ-010': 'ICD 编码不可见',
  'NLQ-011': '回答选项上限 (≤5)',
  // NQ-001..006 (Necessity Gate)
  'NQ-001': '必要性: 证据充分性',
  'NQ-002': '必要性: 临床相关性',
  'NQ-003': '必要性: 答复可行性',
  'NQ-004': '必要性: 病历影响',
  'NQ-005': '必要性: 重复风险',
  'NQ-006': '必要性: 过度问询预警',
  // SD-001..003 (Single-Dimension Gate)
  'SD-001': '单维度: 主题多轴',
  'SD-002': '单维度: 文本多轴',
  'SD-003': '单维度: 轴线聚集',
  // CEA-001..009 (Claim-Evidence Alignment)
  'CEA-001': '证据-声明: 引用存在于病历',
  'CEA-002': '证据-声明: 字符定位准确',
  'CEA-003': '证据-声明: 文档 ID 有效',
  'CEA-004': '证据-声明: 非跨病例证据',
  'CEA-005': '证据-声明: 非否定为肯定',
  'CEA-006': '证据-声明: 非既往史当作现病史',
  'CEA-007': '证据-声明: 推断不可标记为直接',
  'CEA-008': '证据-声明: 关键声明必有证据',
  'CEA-009': '证据-声明: 仅有推断的关键声明降级',
};

export function labelRuleId(id: string | undefined): string {
  if (!id) return '';
  // Pass through anything that's not in the catalog (forward-compat for
  // future rule IDs). The caller decides whether to display the raw ID
  // (audit mode) or the friendly label (business mode).
  return RULE_ID_LABELS[id] ?? id;
}

/**
 * Map a list of raw rule IDs to friendly Chinese descriptions.
 * Used by the audit panel to render nlq_gate_block_reasons[] without
 * leaking raw "NLQ-001" tokens to clinicians.
 */
export function labelRuleIds(ids: string[] | undefined | null): string[] {
  if (!ids || ids.length === 0) return [];
  return ids.map(labelRuleId);
}

// ---------------------------------------------------------------------------
// Semantic necessity verdict (Gate 4)
// ---------------------------------------------------------------------------

export const SEMANTIC_VERDICT_LABELS: Record<string, string> = {
  PASS: '通过',
  REVIEW_REQUIRED: '需人工复核',
  BLOCK: '阻断',
  DEGRADED: '降级',
};

export function labelSemanticVerdict(v: string | undefined): string {
  if (!v) return '—';
  return SEMANTIC_VERDICT_LABELS[v] ?? v;
}

export const SEMANTIC_REASON_LABELS: Record<string, string> = {
  INSUFFICIENT_CLINICAL_SUBSTRATE: '病历临床基质不足',
  NOT_ANSWERABLE: '当前就诊无法答复',
  REDUNDANT_WITH_CHART: '与病历已有内容重复',
  NO_DOCUMENTATION_IMPACT: '不改变病历记录',
  POSSIBLE_DIAGNOSIS_INVENTION: '可能引导编造诊断',
};

export function labelSemanticReason(code: string | undefined): string {
  if (!code) return '';
  return SEMANTIC_REASON_LABELS[code] ?? code;
}
