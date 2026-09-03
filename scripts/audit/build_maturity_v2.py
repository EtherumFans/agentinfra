"""Build product_maturity_v2.json — multi-axis per-scenario maturity."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DST = REPO / 'reports' / 'comprehensive-audit' / 'phase-a0.1' / 'product_maturity_v2.json'

# Multi-axis maturity model:
#   axis 1: code_maturity (L1..L11, same as v1)
#   axis 2: quality_evidence (SMOKE_ONLY / FORMAL_BENCHMARK / CLINICAL_AUDIT / NONE)
#   axis 3: partner_validation (NONE / SYNTHETIC_E2E / REAL_PARTNER / PRODUCTION_PARTNER)
#   axis 4: regulatory (NONE / SELF_ATTESTED / CERTIFIED)
#   axis 5: workflow_closure (OPEN_LOOP / CLOSED_LOOP / N_A)

SCENARIOS = [
    {
        'id': 'CN-01', 'name': 'Medical Coding (ICD-10-CN)',
        'claim_source': 'CLAUDE.md §两个核心业务入口; Phase 5 Track C/H',
        'code_maturity': 'L4_RUNTIME_REACHABLE',
        'code_maturity_rationale': 'HybridCodingAdapter runs end-to-end via agent_run endpoint with real DeepSeek. L5 not met because integration test on primary path is a 5-case smoke (per A0-P0-013).',
        'quality_evidence': 'SMOKE_ONLY',
        'quality_evidence_rationale': 'Phase A0 v1 labeled this L8_QUALITY_BENCHMARKED on the basis of Phase 5 Track H 40-case Corti calibration + iCoDer 201-case baseline. BUT A0-P0-013 explicitly states "no 201-case baseline" and "Only F1@1=0.15 on 5-case smoke". The two Phase A0 deliverables contradict each other. Phase A0.1 treats A0-P0-013 (the issue ledger) as authoritative because it is machine-derivable from the test fixtures; v1 L8 was self-attested by the maturity author.',
        'partner_validation': 'SYNTHETIC_E2E',
        'partner_validation_rationale': 'Phase 7 Gate 12 partner reference app ran a synthetic fracture case (D86.000+S22.400) against real DeepSeek. Real partner: 0.',
        'regulatory': 'NONE',
        'regulatory_rationale': 'No 等保2.0 三级, no GB/T 35273, no NMPA classification.',
        'workflow_closure': 'OPEN_LOOP',
        'workflow_closure_rationale': 'Output produced; no clinician sign-off; no writeback loop to HIS/EMR.',
        'pre_a0_claim': 'L7_WORKFLOW_CLOSED (implicit)',
        'v1_phase_a0_claim': 'L8_QUALITY_BENCHMARKED',
        'v2_phase_a0_1_correction': 'Multi-axis: code=L4 / quality=SMOKE_ONLY / partner=SYNTHETIC_E2E / regulatory=NONE / workflow=OPEN_LOOP. v1 L8 overstated.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-006 cost=0 bug', 'A0-P0-013 F1 baseline only 5-case smoke', 'A0-P0-007 CDI loop open ( Medical Coding cannot close until upstream CDI closes)'],
    },
    {
        'id': 'CN-02', 'name': 'Clinical Documentation Improvement (CDI)',
        'claim_source': 'CLAUDE.md §两个核心业务入口; Phase 5 Track D/H',
        'code_maturity': 'L4_RUNTIME_REACHABLE',
        'code_maturity_rationale': '12-state CDI lifecycle runs end-to-end with real DeepSeek prompts.',
        'quality_evidence': 'SMOKE_ONLY',
        'quality_evidence_rationale': 'Track H iterations 1-7 ran 40-case Corti calibration but no formal quality benchmark and no clinician sign-off.',
        'partner_validation': 'NONE',
        'partner_validation_rationale': 'No partner has run CDI in any form.',
        'regulatory': 'NONE',
        'regulatory_rationale': 'No certification, no clinical audit.',
        'workflow_closure': 'OPEN_LOOP',
        'workflow_closure_rationale': 'A0-P0-007: 443 queries emitted, 0 clinician responses, 0 document revisions. CDI loop is architecturally open by definition — CDI safety claim cannot be made until at least one clinician response is captured.',
        'pre_a0_claim': 'L7_WORKFLOW_CLOSED (implicit)',
        'v1_phase_a0_claim': 'L4_RUNTIME_REACHABLE',
        'v2_phase_a0_1_correction': 'Multi-axis: code=L4 / quality=SMOKE_ONLY / partner=NONE / regulatory=NONE / workflow=OPEN_LOOP (explicit). v1 L4 was correct on code axis but did not flag workflow as OPEN_LOOP loudly enough.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-007 CDI open loop'],
    },
    {
        'id': 'CN-03', 'name': 'DRG/DIP grouping',
        'claim_source': 'CLAUDE.md §医疗收入合规体系; Gate 5',
        'code_maturity': 'L3_CODE_PRESENT',
        'code_maturity_rationale': 'DRG code real but unused (A0-P1-017). DIP returns 501 / demo HTML (A0-P1-018).',
        'quality_evidence': 'NONE',
        'partner_validation': 'NONE',
        'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L4_RUNTIME_REACHABLE (per rule presence)',
        'v1_phase_a0_claim': 'L3_CODE_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1 L3.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P1-017 DRG unused', 'A0-P1-018 DIP demo only'],
    },
    {
        'id': 'CN-04', 'name': 'Insurance Audit (W-4)',
        'code_maturity': 'L1_ASSET_PRESENT',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L3_CODE_PRESENT', 'v1_phase_a0_claim': 'L1_ASSET_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1 L1.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P1-039'],
    },
    {
        'id': 'CN-05', 'name': 'Charge Compliance (W-5)',
        'code_maturity': 'L1_ASSET_PRESENT',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L2_CONTRACT_PRESENT', 'v1_phase_a0_claim': 'L1_ASSET_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1 L1.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P1-040'],
    },
    {
        'id': 'CN-06', 'name': 'Document Evidence (W-6)',
        'code_maturity': 'L1_ASSET_PRESENT',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L1_ASSET_PRESENT', 'v1_phase_a0_claim': 'L1_ASSET_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1.',
        'cn_relevant': True,
    },
    {
        'id': 'CN-07', 'name': 'ICD-9-CM-3 Procedure Coding',
        'code_maturity': 'L4_RUNTIME_REACHABLE',
        'code_maturity_rationale': 'Procedure agent is runnable; depth lacking.',
        'quality_evidence': 'SMOKE_ONLY', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'OPEN_LOOP',
        'pre_a0_claim': 'L5_INTEGRATION_VERIFIED', 'v1_phase_a0_claim': 'L4_RUNTIME_REACHABLE',
        'v2_phase_a0_1_correction': 'Confirms v1 L4; adds multi-axis.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P1-041'],
    },
    {
        'id': 'CN-08', 'name': 'AuditLog / RunHistory traceability',
        'code_maturity': 'L3_CODE_PRESENT',
        'code_maturity_rationale': 'Code present; RUNTRACE_STORE=memory default (A0-P0-008) means table empty; audit_logs records only 5 actions (A0-P0-011); 235/240 run_history rows NULL organization_id (A0-P0-012).',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L7_WORKFLOW_CLOSED (implicit)', 'v1_phase_a0_claim': 'L3_CODE_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1 L3.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-008', 'A0-P0-011', 'A0-P0-012'],
    },
    {
        'id': 'CN-09', 'name': 'Billing / Usage / Cost',
        'code_maturity': 'L2_CONTRACT_PRESENT',
        'code_maturity_rationale': 'Endpoints exist, UI exists. 0 transactions, fake ¥50 balance, cost=0 bug.',
        'quality_evidence': 'NONE',
        'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L4_RUNTIME_REACHABLE', 'v1_phase_a0_claim': 'L2_CONTRACT_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1 L2.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-004', 'A0-P0-006', 'A0-P0-009'],
    },
    {
        'id': 'CN-10', 'name': '等保2.0 三级 compliance',
        'code_maturity': 'L1_ASSET_PRESENT',
        'code_maturity_rationale': 'Mentioned in CLAUDE.md and reports. No certification, no technical controls.',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE',
        'regulatory': 'NONE',
        'regulatory_rationale': 'Self-attested mention is not certification. A0-P0-001 documents zero certs.',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L1_ASSET_PRESENT', 'v1_phase_a0_claim': 'L1_ASSET_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-001', 'A0-P0-002', 'A0-P0-016', 'A0-P0-017'],
    },
    {
        'id': 'CN-11', 'name': 'Embedded SDK (Web Component)',
        'code_maturity': 'L6_BROWSER_VERIFIED',
        'code_maturity_rationale': 'Phase 7 Gate 10/11/12 browser-verified with real DeepSeek run.',
        'quality_evidence': 'NONE',
        'partner_validation': 'SYNTHETIC_E2E',
        'partner_validation_rationale': 'Phase 7 Gate 12 partner reference app. Real partner: 0.',
        'regulatory': 'NONE',
        'workflow_closure': 'OPEN_LOOP',
        'workflow_closure_rationale': 'Widget runs and emits events; no HIS/EMR writeback integration in production.',
        'pre_a0_claim': 'L7_WORKFLOW_CLOSED', 'v1_phase_a0_claim': 'L6_BROWSER_VERIFIED',
        'v2_phase_a0_1_correction': 'Confirms v1 L6; adds multi-axis.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-009 npm unpublished', 'A0-P0-018/019 Gate 13A security evidence regraded to E1'],
    },
    {
        'id': 'CN-12', 'name': 'Multi-tenant isolation',
        'code_maturity': 'L3_CODE_PRESENT',
        'code_maturity_rationale': '235/240 rows NULL organization_id (A0-P0-012); tenant extractor cloud-mode-only; design-only.',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L5_INTEGRATION_VERIFIED', 'v1_phase_a0_claim': 'L3_CODE_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1 L3.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-012', 'A0-P0-022'],
    },
    {
        'id': 'CN-13', 'name': 'Partner Reference App',
        'code_maturity': 'L6_BROWSER_VERIFIED',
        'code_maturity_rationale': 'Phase 7 Gate 12 E2E verified real DeepSeek run; synthetic data.',
        'quality_evidence': 'NONE', 'partner_validation': 'SYNTHETIC_E2E', 'regulatory': 'NONE',
        'workflow_closure': 'OPEN_LOOP',
        'pre_a0_claim': 'L7_WORKFLOW_CLOSED', 'v1_phase_a0_claim': 'L6_BROWSER_VERIFIED',
        'v2_phase_a0_1_correction': 'Confirms v1 L6; adds multi-axis.',
        'cn_relevant': True,
    },
    {
        'id': 'CN-14', 'name': 'Corti-style Agent Hub',
        'code_maturity': 'L6_BROWSER_VERIFIED',
        'code_maturity_rationale': 'Hub browsable, clone/create work; 25 Hub-visible agents, 15 metadata-only.',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'OPEN_LOOP',
        'pre_a0_claim': 'L7_WORKFLOW_CLOSED', 'v1_phase_a0_claim': 'L6_BROWSER_VERIFIED',
        'v2_phase_a0_1_correction': 'Confirms v1 L6 (not L7 because most agents metadata-only).',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-014', 'A0-P1-019'],
    },
    {
        'id': 'CN-15', 'name': 'A2A v0.3 Protocol',
        'code_maturity': 'L4_RUNTIME_REACHABLE',
        'code_maturity_rationale': 'A2A envelope in main path works. Tasks stub returns 501.',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L5_INTEGRATION_VERIFIED', 'v1_phase_a0_claim': 'L4_RUNTIME_REACHABLE',
        'v2_phase_a0_1_correction': 'Confirms v1 L4.',
        'cn_relevant': False,
        'blocking_findings': ['A0-P1-009'],
    },
    {
        'id': 'CN-16', 'name': 'PHI redaction',
        'code_maturity': 'L3_CODE_PRESENT',
        'code_maturity_rationale': 'Per Gate 9 K3.2: EXPORT-PATH ONLY. Live path bypasses.',
        'quality_evidence': 'NONE', 'partner_validation': 'NONE', 'regulatory': 'NONE',
        'workflow_closure': 'N_A',
        'pre_a0_claim': 'L5_INTEGRATION_VERIFIED', 'v1_phase_a0_claim': 'L3_CODE_PRESENT',
        'v2_phase_a0_1_correction': 'Confirms v1 L3. Pre-A0 inverted this as iCoDer advantage; corrected.',
        'cn_relevant': True,
        'blocking_findings': ['A0-P0-017'],
    },
]

# Compute summary
from collections import Counter
code_dist = Counter(s['code_maturity'] for s in SCENARIOS)
quality_dist = Counter(s['quality_evidence'] for s in SCENARIOS)
partner_dist = Counter(s['partner_validation'] for s in SCENARIOS)
reg_dist = Counter(s['regulatory'] for s in SCENARIOS)
closure_dist = Counter(s['workflow_closure'] for s in SCENARIOS)

LADDER = ['L1_ASSET_PRESENT','L2_CONTRACT_PRESENT','L3_CODE_PRESENT','L4_RUNTIME_REACHABLE',
          'L5_INTEGRATION_VERIFIED','L6_BROWSER_VERIFIED','L7_WORKFLOW_CLOSED','L8_QUALITY_BENCHMARKED',
          'L9_CLINICALLY_REVIEWED','L10_EXTERNAL_PARTNER_VALIDATED','L11_DEPLOYMENT_VALIDATED']

def above(s, level):
    return LADDER.index(s) >= LADDER.index(level)

v2 = {
    '$schema': 'https://icoder.cloud/schemas/audit/product-maturity-v2.json',
    'schema_version': '2.0',
    'generated_at': '2026-07-17',
    'generated_by': 'Phase A0.1 Gate 5 - Product Maturity V2',
    'supersedes': 'reports/comprehensive-audit/phase-a0/product_maturity.json (v1, Phase A0 Gate 6)',
    'maturity_scale_v1': {
        'L1_ASSET_PRESENT': 'File exists on disk',
        'L2_CONTRACT_PRESENT': 'API endpoint or schema exists but no implementation',
        'L3_CODE_PRESENT': 'Implementation code exists but not wired',
        'L4_RUNTIME_REACHABLE': 'Code is wired and can be invoked',
        'L5_INTEGRATION_VERIFIED': 'Integration test passes',
        'L6_BROWSER_VERIFIED': 'Live browser walkthrough succeeds',
        'L7_WORKFLOW_CLOSED': 'End-to-end workflow completes with feedback loop',
        'L8_QUALITY_BENCHMARKED': 'Formal quality benchmark passes',
        'L9_CLINICALLY_REVIEWED': 'Real clinician sign-off',
        'L10_EXTERNAL_PARTNER_VALIDATED': 'Real partner or production user',
        'L11_DEPLOYMENT_VALIDATED': 'Validated in production',
    },
    'design_principles_v2': [
        'multi_axis_per_scenario_not_single_L',
        'quality_evidence_axis_separates_smoke_from_benchmark',
        'workflow_closure_axis_makes_open_loop_explicit',
        'regulatory_axis_separates_self_attested_from_certified',
        'v1_L8_claim_requires_machines_verifiable_F1_report_not_self_attestation',
    ],
    'multi_axis_definition': {
        'code_maturity': 'Single L1-L11 level per v1 scale',
        'quality_evidence': ['NONE', 'SMOKE_ONLY', 'FORMAL_BENCHMARK', 'CLINICAL_AUDIT'],
        'partner_validation': ['NONE', 'SYNTHETIC_E2E', 'REAL_PARTNER', 'PRODUCTION_PARTNER'],
        'regulatory': ['NONE', 'SELF_ATTESTED', 'CERTIFIED'],
        'workflow_closure': ['N_A', 'OPEN_LOOP', 'CLOSED_LOOP'],
    },
    'china_scenarios': SCENARIOS,
    'summary': {
        'total_scenarios': len(SCENARIOS),
        'code_maturity_distribution': {k: code_dist.get(k, 0) for k in LADDER},
        'quality_evidence_distribution': {k: quality_dist.get(k, 0) for k in ['NONE','SMOKE_ONLY','FORMAL_BENCHMARK','CLINICAL_AUDIT']},
        'partner_validation_distribution': {k: partner_dist.get(k, 0) for k in ['NONE','SYNTHETIC_E2E','REAL_PARTNER','PRODUCTION_PARTNER']},
        'regulatory_distribution': {k: reg_dist.get(k, 0) for k in ['NONE','SELF_ATTESTED','CERTIFIED']},
        'workflow_closure_distribution': {k: closure_dist.get(k, 0) for k in ['N_A','OPEN_LOOP','CLOSED_LOOP']},
        'v1_vs_v2_regrades': {
            'CN-01_Medical_Coding': {
                'v1_claim': 'L8_QUALITY_BENCHMARKED',
                'v2_correction': 'code=L4, quality=SMOKE_ONLY',
                'reason': 'v1 L8 was based on Phase 5 Track H 40-case Corti calibration + claimed 201-case baseline. A0-P0-013 in the same Phase A0 issue ledger explicitly states "Only F1@1=0.15 on 5-case smoke; no 201-case baseline". The two Phase A0 deliverables contradict each other. v2 treats A0-P0-013 as authoritative because it is machine-derivable from test fixtures.',
                'severity': 'P0-C (clinical safety overclaim)',
            },
            'CN-02_CDI': {
                'v1_claim': 'L4_RUNTIME_REACHABLE',
                'v2_correction': 'code=L4 confirmed; workflow_closure=OPEN_LOOP made explicit',
                'reason': 'v1 was correct on code axis but did not loudly enough mark workflow as OPEN_LOOP. Per A0-P0-007 443 queries emitted / 0 clinician responses.',
                'severity': 'P0-C',
            },
        },
        'scenarios_at_L7_plus': sum(1 for s in SCENARIOS if above(s['code_maturity'], 'L7_WORKFLOW_CLOSED')),
        'scenarios_at_L6_plus': sum(1 for s in SCENARIOS if above(s['code_maturity'], 'L6_BROWSER_VERIFIED')),
        'scenarios_with_quality_benchmark': sum(1 for s in SCENARIOS if s['quality_evidence'] in ('FORMAL_BENCHMARK','CLINICAL_AUDIT')),
        'scenarios_with_open_loop': sum(1 for s in SCENARIOS if s['workflow_closure'] == 'OPEN_LOOP'),
        'scenarios_with_real_partner': sum(1 for s in SCENARIOS if s['partner_validation'] in ('REAL_PARTNER','PRODUCTION_PARTNER')),
    },
    'readiness_tracks_v2': {
        'INTERNAL_DEMO': {
            'achieved': True,
            'scenarios_supporting': ['CN-01','CN-11','CN-13','CN-14'],
            'caveat': 'Internal demos work against real DeepSeek with synthetic data.',
        },
        'CUSTOMER_DEMO': {
            'achieved': False,
            'blockers': ['A0-P0-005 Corti redirects visible to buyer','A0-P0-015 strategic incoherence','A0-P0-006 cost=0 bug visible'],
        },
        'PARTNER_TECHNICAL_STAGING': {
            'achieved': False,
            'blockers': ['A0-P0-009 npm unpublished','A0-P0-021 supply chain unsigned'],
            'caveat': 'Synthetic E2E achieved (CN-11, CN-13); real partner integration not.',
        },
        'HOSPITAL_RESEARCH_SANDBOX': {
            'achieved': False,
            'blockers': ['A0-P0-001 no cert','A0-P0-002 no legal docs','A0-P0-016 no encryption at rest','A0-P0-017 PHI export-only'],
        },
        'HOSPITAL_CLINICAL_WORKFLOW_PILOT': {
            'achieved': False,
            'blockers': ['All P0-S','All P0-C (CDI loop, F1 baseline)','A0-P0-003 no deployment path'],
            'caveat': 'CN-01 Medical Coding at SMOKE_ONLY quality and OPEN_LOOP workflow cannot enter clinical workflow.',
        },
        'COMMERCIAL_GA': {
            'achieved': False,
            'blockers': ['All P0','A0-P0-004 billing theater','A0-P0-009 npm unpublished'],
        },
    },
    'verdict': {
        'tier': 'CONDITIONALLY_ACHIEVABLE',
        'achieved_today': 'INTERNAL_DEMO only',
        'multi_axis_headline': '1 scenario at code=L6+ with quality=NONE; 0 scenarios at quality=FORMAL_BENCHMARK or CLINICAL_AUDIT; 7 scenarios at workflow=OPEN_LOOP; 0 scenarios with REAL_PARTNER validation.',
        'next_phase_target': 'A1 lifts CN-01 from SMOKE_ONLY to FORMAL_BENCHMARK (201-case) AND CN-02 from OPEN_LOOP to first clinician response captured.',
    },
}

with DST.open('w', encoding='utf-8') as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f'v2 maturity written: {len(SCENARIOS)} scenarios')
print(f'code_maturity_distribution: {v2["summary"]["code_maturity_distribution"]}')
print(f'quality_evidence_distribution: {v2["summary"]["quality_evidence_distribution"]}')
print(f'workflow_closure_distribution: {v2["summary"]["workflow_closure_distribution"]}')
print(f'scenarios_at_L7_plus: {v2["summary"]["scenarios_at_L7_plus"]}')
print(f'scenarios_with_quality_benchmark: {v2["summary"]["scenarios_with_quality_benchmark"]}')
