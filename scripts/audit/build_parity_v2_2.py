"""Build parity_matrix_v2_2.json from v2.1 — re-derive counts, fix typos, apply thresholds."""
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / 'reports' / 'comprehensive-audit' / 'phase-a0' / 'parity_matrix_v2_1.json'
DST = REPO / 'reports' / 'comprehensive-audit' / 'phase-a0.1' / 'parity_matrix_v2_2.json'

with SRC.open(encoding='utf-8') as f:
    v21 = json.load(f)

THRESHOLDS = {
    'Runtime': 'E4',
    'Security': 'E7',
    'Clinical': 'BENCHMARK_OR_CLINICAL_AUDIT',
}

DOWNGRADES = {
    'A-09': ('Runtime', 'E3', 'Threshold E4 not met; E3 = unit-verified only, not integration-verified'),
    'A-10': ('Runtime', 'E3', 'Threshold E4 not met; E3 = unit-verified only; also RunHistory table empty per A0-P0-008'),
    'C-12': ('Clinical', 'E2', 'No formal benchmark or clinical audit on file; E2 code-observed only'),
    'C-13': ('Clinical', 'E2', 'No formal benchmark; DRG-DIP rules are reserved not exercised in production'),
    'G-01': ('Runtime', 'E2', 'Threshold E4 not met; RUNTRACE_STORE=memory default per A0-P0-008, table empty'),
    'G-02': ('Runtime', 'E3', 'Threshold E4 not met; E3 = unit-verified only'),
    'G-03': ('Runtime', 'E3', 'Threshold E4 not met; 235/240 rows have NULL organization_id per A0-P0-012'),
    'G-04': ('Runtime', 'E2', 'Threshold E4 not met; E2 = code-observed only'),
    'G-05': ('Runtime', 'E2', 'Threshold E4 not met; E2 = code-observed only'),
}

new_dims = []
regrade_log = []

for d in v21['dimensions']:
    nd = dict(d)
    if 'icorer_evidence_grade' in nd:
        nd['icoder_evidence_grade'] = nd.pop('icorer_evidence_grade')
        nd['v2_2_typo_fix'] = 'was icorer_evidence_grade in v2.1 (field name typo)'
    if nd.get('parity_status') == 'ICODER_ADVANTAGE' and nd['id'] in DOWNGRADES:
        bucket, grade, reason = DOWNGRADES[nd['id']]
        old = nd['parity_status']
        nd['parity_status'] = 'EVIDENCE_INSUFFICIENT'
        nd['claim_intent'] = 'ICODER_ADVANTAGE'
        nd['claim_blocked_by_threshold'] = bucket
        nd['claim_threshold_required'] = THRESHOLDS[bucket]
        nd['claim_threshold_current'] = grade
        nd['claim_threshold_rationale'] = reason
        regrade_log.append({
            'id': nd['id'],
            'name': nd['name'],
            'class': nd['class'],
            'bucket': bucket,
            'threshold': THRESHOLDS[bucket],
            'current': grade,
            'old_status': old,
            'new_status': 'EVIDENCE_INSUFFICIENT',
            'rationale': reason,
        })
    new_dims.append(nd)

status_counter = Counter(d['parity_status'] for d in new_dims)
ic_grades = Counter(d.get('icoder_evidence_grade', '?') for d in new_dims)
co_grades = Counter(d.get('corti_evidence_grade', '?') for d in new_dims)

v22 = {
    '$schema': 'https://icoder.cloud/schemas/audit/parity-matrix-v2-2.json',
    'schema_version': '2.2',
    'generated_at': '2026-07-17',
    'generated_by': 'Phase A0.1 Gate 4 - Parity Matrix V2.2',
    'supersedes': 'reports/comprehensive-audit/phase-a0/parity_matrix_v2_1.json (v2.1, Phase A0 Gate 4)',
    'design_principles': v21['design_principles'],
    'design_principles_v2_2_additions': [
        'summary_counts_are_array_derived_no_narrative_numbers',
        'evidence_grade_thresholds_gate_advantage_claims',
        'typo_in_field_name_is_an_audit_bug_not_an_oversight',
        'icoder_advantage_pending_evidence_is_not_advantage',
    ],
    'allowed_statuses': v21['allowed_statuses'],
    'evidence_grades': v21['evidence_grades'],
    'evidence_grade_thresholds_for_advantage': {
        'Runtime_advantage_minimum': 'E4 (integration-verified)',
        'Security_advantage_minimum': 'E7 (security-negative-verified)',
        'Clinical_advantage_minimum': 'formal benchmark or clinical audit on file (in addition to code-observed E2)',
        'UX_or_product_advantage_minimum': 'E5 (browser-verified) - same as v2.1',
        'Tool_catalog_advantage_minimum': 'E2 (code-observed) - tool counts do not require integration verification',
        'rationale': 'Phase A0 v2.1 claimed ICODER_ADVANTAGE on 11 dimensions but 9 of them sat at E2/E3 with no integration evidence. Phase A0.1 Gate 4 enforces explicit thresholds: an unverified advantage is not an advantage.',
    },
    'dimensions': new_dims,
    'summary': {
        'total_dimensions': len(new_dims),
        'total_dimensions_formula': 'len(dimensions) - machine-derived',
        'by_status': dict(sorted(status_counter.items(), key=lambda x: -x[1])),
        'by_status_sum_check': sum(status_counter.values()),
        'by_evidence_grade_icoder': {g: ic_grades.get(g, 0) for g in ['E0','E1','E2','E3','E4','E5','E6','E7','E8']},
        'by_evidence_grade_corti': {g: co_grades.get(g, 0) for g in ['E0','E1','E2','E3','E4','E5','E6','E7','E8']},
        'what_phase_a0_v2_1_summary_claimed_vs_actual': {
            'v2_1_claimed_total_dimensions': v21['summary']['total_dimensions'],
            'v2_1_actual_array_count': len(v21['dimensions']),
            'delta': len(v21['dimensions']) - v21['summary']['total_dimensions'],
            'v2_1_claimed_by_status_sum': sum(v21['summary']['by_status'].values()),
            'v2_1_actual_array_count_derived': len(v21['dimensions']),
            'verdict': 'v2.1 summary undercount by 8 dimensions; v2.2 corrects',
        },
        'what_phase_a0_does_NOT_report': v21['summary']['what_phase_a0_does_NOT_report'],
        'cn_relevant_dimensions': sum(1 for d in new_dims if d.get('cn_relevant')),
        'cn_relevant_with_severe_gap': sum(1 for d in new_dims if d.get('cn_relevant') and d.get('severity_if_gap','n/a') not in ('n/a', None, 'P3')),
    },
    'regrade_log': regrade_log,
    'vs_v2_1_changes': {
        'v2_1_summary_total_dimensions_51': 'INVALIDATED - array had 59 dimensions; v2.1 summary undercount by 8',
        'v2_1_A_05_typo_icorer_evidence_grade': 'FIXED - field name corrected to icoder_evidence_grade',
        'v2_1_icoder_advantage_count_11': 'REDUCED to 2 (B-10 Badge taxonomy E5, D-04 MCP handler count E2) - 9 entries downgraded to EVIDENCE_INSUFFICIENT because evidence below advantage threshold',
        'v2_1_evidence_insufficient_count_4': 'INCREASED to 13 (4 original + 9 downgraded advantage claims)',
        'v2_1_partical_parity_7_count': 'array shows 6 (typo or miscount in v2.1 summary)',
    },
}

assert v22['summary']['total_dimensions'] == 59, f"Got {v22['summary']['total_dimensions']}"
assert sum(v22['summary']['by_status'].values()) == 59

with DST.open('w', encoding='utf-8') as f:
    json.dump(v22, f, ensure_ascii=False, indent=2)

print(f'v2.2 written: {len(new_dims)} dimensions')
print(f'ICODER_ADVANTAGE remaining: {status_counter["ICODER_ADVANTAGE"]}')
print(f'EVIDENCE_INSUFFICIENT: {status_counter["EVIDENCE_INSUFFICIENT"]}')
print(f'by_status: {dict(sorted(status_counter.items(), key=lambda x: -x[1]))}')
print(f'ICODER grades: {dict(sorted(ic_grades.items()))}')
print(f'CORTI grades: {dict(sorted(co_grades.items()))}')
print(f'Regrade log: {len(regrade_log)} entries')
