"""Phase 5 Track B-2 Phase 11 — Aggregator.

Reads per-agent run envelopes + reports + manual scores to emit:
- outputs/phase5_track_b2/agent_ux_matrix_b2.csv (12 UX dim x 9 agents)
- outputs/phase5_track_b2/agent_capability_matrix_b2.csv (5 layers x 9 agents)
- outputs/phase5_track_b2/agent_integration_matrix_b2.csv (16 dim x 9 agents)
- outputs/phase5_track_b2/gap_backlog.jsonl
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

AGENT_DIRS = [
    ('medical-coding-agent', 'CP1'),
    ('code-validation-agent', 'CP2'),
    ('compliance-guardrail-agent', 'CP3'),
    ('note-completeness-agent', 'CP4'),
    ('procedure-extractor', 'CP5'),
    ('evidence-extractor', 'CP6'),
    ('principal-diagnosis-review', 'CP7'),
    ('discharge-summary-structuring', 'CP8'),
    ('drg-analyzer', 'CP9'),
]

# UX scores from each CP report (12 dimensions x 9 agents)
# Pulled from report §27 (or §29 for CP8/CP9)
UX_SCORES = {
    'medical-coding-agent': {
        'entry_discoverability': 4, 'input_experience': 4, 'output_readability': 4,
        'error_recovery': 4, 'realtime_feedback': 4, 'trace_transparency': 3,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
    'code-validation-agent': {
        'entry_discoverability': 4, 'input_experience': 3, 'output_readability': 3,
        'error_recovery': 4, 'realtime_feedback': 2, 'trace_transparency': 2,
        'cost_transparency': 2, 'copy_download': 5, 'configurable': 3,
        'multi_turn': 3, 'mobile_response': 3, 'i18n': 3,
    },
    'compliance-guardrail-agent': {
        'entry_discoverability': 4, 'input_experience': 3, 'output_readability': 4,
        'error_recovery': 4, 'realtime_feedback': 4, 'trace_transparency': 2,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
    'note-completeness-agent': {
        'entry_discoverability': 4, 'input_experience': 4, 'output_readability': 4,
        'error_recovery': 5, 'realtime_feedback': 4, 'trace_transparency': 2,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
    'procedure-extractor': {
        'entry_discoverability': 4, 'input_experience': 4, 'output_readability': 4,
        'error_recovery': 5, 'realtime_feedback': 3, 'trace_transparency': 2,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
    'evidence-extractor': {
        'entry_discoverability': 4, 'input_experience': 3, 'output_readability': 4,
        'error_recovery': 5, 'realtime_feedback': 4, 'trace_transparency': 2,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
    'principal-diagnosis-review': {
        'entry_discoverability': 4, 'input_experience': 4, 'output_readability': 5,
        'error_recovery': 5, 'realtime_feedback': 3, 'trace_transparency': 2,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
    'discharge-summary-structuring': {
        'entry_discoverability': 4, 'input_experience': 4, 'output_readability': 4,
        'error_recovery': 5, 'realtime_feedback': 3, 'trace_transparency': 2,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
    'drg-analyzer': {
        'entry_discoverability': 4, 'input_experience': 3, 'output_readability': 5,
        'error_recovery': 5, 'realtime_feedback': 3, 'trace_transparency': 2,
        'cost_transparency': 5, 'copy_download': 5, 'configurable': 4,
        'multi_turn': 4, 'mobile_response': 3, 'i18n': 4,
    },
}

# Capability layers (5 layers x 9 agents) from §28 / §30
CAPABILITY = {
    'medical-coding-agent': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek 4-8s)',
        'RESULT_CONSUMED': 'Y (structured)',
        'QUALITY_VALIDATED': 'Y',
        'top': 'QUALITY_VALIDATED',
    },
    'code-validation-agent': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'SKELETON (llm-with-tools.v1 not implemented)',
        'RESULT_CONSUMED': 'N/A',
        'QUALITY_VALIDATED': 'N/A',
        'top': 'AGENT_CONFIGURED',
    },
    'compliance-guardrail-agent': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek + RuleEngine)',
        'RESULT_CONSUMED': 'Partial (markdown JSON)',
        'QUALITY_VALIDATED': 'Y',
        'top': 'RESULT_CONSUMED',
    },
    'note-completeness-agent': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek 8.9-10.9s)',
        'RESULT_CONSUMED': 'Partial (JSON-in-markdown)',
        'QUALITY_VALIDATED': 'Partial (repeatability 400 delta)',
        'top': 'RESULT_CONSUMED',
    },
    'procedure-extractor': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek)',
        'RESULT_CONSUMED': 'Partial (JSON-in-markdown)',
        'QUALITY_VALIDATED': 'Y (per-dept accurate)',
        'top': 'RESULT_CONSUMED',
    },
    'evidence-extractor': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek 5.5-6.7s)',
        'RESULT_CONSUMED': 'Partial (JSON-in-markdown)',
        'QUALITY_VALIDATED': 'Partial (repeatability 22 delta)',
        'top': 'RESULT_CONSUMED',
    },
    'principal-diagnosis-review': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek 4.8-16.8s)',
        'RESULT_CONSUMED': 'Partial (JSON-in-markdown)',
        'QUALITY_VALIDATED': 'Y (conflict resolution accurate)',
        'top': 'RESULT_CONSUMED',
    },
    'discharge-summary-structuring': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek 6.8-10.2s)',
        'RESULT_CONSUMED': 'Partial (JSON-in-markdown)',
        'QUALITY_VALIDATED': 'Y (repeatability delta < 90)',
        'top': 'RESULT_CONSUMED',
    },
    'drg-analyzer': {
        'PLATFORM_AVAILABLE': 'Y', 'AGENT_CONFIGURED': 'Y',
        'RUNTIME_INVOKED': 'Y (real DeepSeek 7.2-15.2s)',
        'RESULT_CONSUMED': 'Partial (JSON-in-markdown)',
        'QUALITY_VALIDATED': 'Partial (run 3 shorter)',
        'top': 'RESULT_CONSUMED',
    },
}

# Integration matrix (16 dimensions x 9 agents)
INTEGRATION = {
    'medical-coding-agent': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y', 'Tool calls (MCP)': 'Y (4 experts + 4 tools)',
        'Backend provider': 'icoder.medical-coding.v1 (HybridCodingAdapter)',
        'Unified API /run': 'Y', 'Trace events': 'Y (multi-step)',
        'Cost tracking': 'Y', 'Embedded smoke': 'Y (4 eligible)',
        'Backend Service Integration': 'READY', 'ROPC Embedded': 'READY',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Y (entry point)',
    },
    'code-validation-agent': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'N (SKELETON)', 'Tool calls (MCP)': 'N (provider not impl)',
        'Backend provider': 'icoder.llm-with-tools.v1 (SKELETON)',
        'Unified API /run': 'Y', 'Trace events': 'Minimal',
        'Cost tracking': 'N (no LLM call)', 'Embedded smoke': 'N',
        'Backend Service Integration': 'NOT READY', 'ROPC Embedded': 'N',
        'RunHistory': 'Y (metadata only)', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (post-impl)',
    },
    'compliance-guardrail-agent': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y', 'Tool calls (MCP)': 'N (rule-based + LLM)',
        'Backend provider': 'icoder.rule-engine.v1',
        'Unified API /run': 'Y', 'Trace events': 'Minimal (1)',
        'Cost tracking': 'Y', 'Embedded smoke': 'N',
        'Backend Service Integration': 'CONDITIONAL READY', 'ROPC Embedded': 'N',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (stage 5)',
    },
    'note-completeness-agent': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y (8.9-10.9s)', 'Tool calls (MCP)': 'N (PureLLM)',
        'Backend provider': 'icoder.pure-llm.v1',
        'Unified API /run': 'Y', 'Trace events': 'Minimal (1)',
        'Cost tracking': 'Y', 'Embedded smoke': 'Y (4 eligible)',
        'Backend Service Integration': 'CONDITIONAL READY', 'ROPC Embedded': 'READY',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (stage 6)',
    },
    'procedure-extractor': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y', 'Tool calls (MCP)': 'N (PureLLM)',
        'Backend provider': 'icoder.pure-llm.v1',
        'Unified API /run': 'Y', 'Trace events': 'Minimal (1)',
        'Cost tracking': 'Y', 'Embedded smoke': 'N',
        'Backend Service Integration': 'CONDITIONAL READY', 'ROPC Embedded': 'N',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (after stage 2)',
    },
    'evidence-extractor': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y (5.5-6.7s)', 'Tool calls (MCP)': 'N (PureLLM)',
        'Backend provider': 'icoder.pure-llm.v1',
        'Unified API /run': 'Y', 'Trace events': 'Minimal (1)',
        'Cost tracking': 'Y', 'Embedded smoke': 'Y (4 eligible)',
        'Backend Service Integration': 'CONDITIONAL READY', 'ROPC Embedded': 'READY',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (stage 4)',
    },
    'principal-diagnosis-review': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y (4.8-16.8s)', 'Tool calls (MCP)': 'N (PureLLM)',
        'Backend provider': 'icoder.pure-llm.v1',
        'Unified API /run': 'Y', 'Trace events': 'Minimal (1)',
        'Cost tracking': 'Y', 'Embedded smoke': 'Y (4 eligible)',
        'Backend Service Integration': 'CONDITIONAL READY', 'ROPC Embedded': 'READY',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (stage 3)',
    },
    'discharge-summary-structuring': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y (6.8-10.2s)', 'Tool calls (MCP)': 'N (PureLLM)',
        'Backend provider': 'icoder.pure-llm.v1',
        'Unified API /run': 'Y', 'Trace events': 'Minimal (1)',
        'Cost tracking': 'Y', 'Embedded smoke': 'N',
        'Backend Service Integration': 'CONDITIONAL READY', 'ROPC Embedded': 'N',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (stage 1)',
    },
    'drg-analyzer': {
        'Hub discoverable': 'Y', 'Detail page 5 tabs': 'Y', 'Chat UI': 'Y',
        'Real DeepSeek': 'Y (7.2-15.2s)', 'Tool calls (MCP)': 'N (PureLLM)',
        'Backend provider': 'icoder.pure-llm.v1',
        'Unified API /run': 'Y', 'Trace events': 'Minimal (1)',
        'Cost tracking': 'Y', 'Embedded smoke': 'N',
        'Backend Service Integration': 'CONDITIONAL READY', 'ROPC Embedded': 'N',
        'RunHistory': 'Y', 'AuditLog': 'Y', 'Fork UI': 'Y',
        'Orchestrator sub-agent': 'Should be (stage 7 - final)',
    },
}

# Gap backlog (per CP reports)
GAPS = [
    # CP1 (medical-coding-agent) — none P1, listed for completeness
    {'gap_id': 'GAP-CP1-01', 'cp': 'CP1', 'agent': 'medical-coding-agent', 'severity': 'P3', 'title': 'trace_events granularity', 'description': 'Per-code trace could be richer'},
    # CP2
    {'gap_id': 'GAP-CP2-01', 'cp': 'CP2', 'agent': 'code-validation-agent', 'severity': 'P0', 'title': 'llm-with-tools.v1 SKELETON not implemented', 'description': 'Provider raises NotImplementedError; agent returns skeleton envelope'},
    {'gap_id': 'GAP-CP2-02', 'cp': 'CP2', 'agent': 'code-validation-agent', 'severity': 'P1', 'title': '4 MCP tools (verify_code/get_guidelines/explore_code/search_codes) not invoked', 'description': 'Backend provider stub'},
    # CP3
    {'gap_id': 'GAP-CP3-01', 'cp': 'CP3', 'agent': 'compliance-guardrail-agent', 'severity': 'P1', 'title': 'R002 rule regex rejects ICD-10-CN 6-digit codes (I10.x00x002)', 'description': 'WHO format vs CN localization mismatch'},
    {'gap_id': 'GAP-CP3-02', 'cp': 'CP3', 'agent': 'compliance-guardrail-agent', 'severity': 'P1', 'title': 'Orchestrator wiring — should be stage 5 sub-agent', 'description': 'Currently standalone'},
    # CP4
    {'gap_id': 'GAP-CP4-01', 'cp': 'CP4', 'agent': 'note-completeness-agent', 'severity': 'P1', 'title': 'Unified API bypasses _parse_llm_json_to_schema', 'description': 'result.issues/risk_flags always empty'},
    {'gap_id': 'GAP-CP4-02', 'cp': 'CP4', 'agent': 'note-completeness-agent', 'severity': 'P2', 'title': 'Repeatability md_len delta 400 (1545-1946)', 'description': 'temp=0 but non-deterministic'},
    {'gap_id': 'GAP-CP4-03', 'cp': 'CP4', 'agent': 'note-completeness-agent', 'severity': 'P3', 'title': 'trace_events only 1 event', 'description': 'No intermediate step traces'},
    {'gap_id': 'GAP-CP4-04', 'cp': 'CP4', 'agent': 'note-completeness-agent', 'severity': 'P1', 'title': 'Orchestrator wiring — should be stage 6 sub-agent', 'description': 'Currently standalone'},
    # CP5
    {'gap_id': 'GAP-CP5-01', 'cp': 'CP5', 'agent': 'procedure-extractor', 'severity': 'P1', 'title': 'Unified API bypasses structured parsing (same as CP4-01)', 'description': 'JSON-in-markdown'},
    {'gap_id': 'GAP-CP5-02', 'cp': 'CP5', 'agent': 'procedure-extractor', 'severity': 'P2', 'title': 'Planned vs unplanned procedure ambiguity', 'description': 'fixture 01 PVP marked planned but extracted as code'},
    {'gap_id': 'GAP-CP5-03', 'cp': 'CP5', 'agent': 'procedure-extractor', 'severity': 'P1', 'title': 'Orchestrator wiring — should be stage 2 sub-agent', 'description': 'Currently standalone'},
    # CP6
    {'gap_id': 'GAP-CP6-01', 'cp': 'CP6', 'agent': 'evidence-extractor', 'severity': 'P2', 'title': 'Repeatability md_len delta 22', 'description': 'Stable but non-deterministic'},
    {'gap_id': 'GAP-CP6-02', 'cp': 'CP6', 'agent': 'evidence-extractor', 'severity': 'P3', 'title': 'trace_events only 1 event', 'description': ''},
    {'gap_id': 'GAP-CP6-03', 'cp': 'CP6', 'agent': 'evidence-extractor', 'severity': 'P1', 'title': 'Unified API bypasses result.coded_evidence', 'description': 'JSON-in-markdown'},
    {'gap_id': 'GAP-CP6-04', 'cp': 'CP6', 'agent': 'evidence-extractor', 'severity': 'P1', 'title': 'Orchestrator wiring — should be stage 4 sub-agent', 'description': 'Currently standalone'},
    # CP7
    {'gap_id': 'GAP-CP7-01', 'cp': 'CP7', 'agent': 'principal-diagnosis-review', 'severity': 'P2', 'title': 'Repeatability md_len delta 8-188', 'description': ''},
    {'gap_id': 'GAP-CP7-02', 'cp': 'CP7', 'agent': 'principal-diagnosis-review', 'severity': 'P2', 'title': 'Missing Corti 4 experts (pubmed/web-search/calculator/coding)', 'description': 'PureLLM no tools'},
    {'gap_id': 'GAP-CP7-03', 'cp': 'CP7', 'agent': 'principal-diagnosis-review', 'severity': 'P3', 'title': 'trace_events only 1 event', 'description': ''},
    {'gap_id': 'GAP-CP7-04', 'cp': 'CP7', 'agent': 'principal-diagnosis-review', 'severity': 'P1', 'title': 'Unified API bypasses structured fields', 'description': 'JSON-in-markdown'},
    {'gap_id': 'GAP-CP7-05', 'cp': 'CP7', 'agent': 'principal-diagnosis-review', 'severity': 'P1', 'title': 'Orchestrator wiring — should be stage 3 sub-agent', 'description': 'Currently standalone'},
    # CP8
    {'gap_id': 'GAP-CP8-01', 'cp': 'CP8', 'agent': 'discharge-summary-structuring', 'severity': 'P2', 'title': 'Repeatability md_len delta 16-90', 'description': ''},
    {'gap_id': 'GAP-CP8-02', 'cp': 'CP8', 'agent': 'discharge-summary-structuring', 'severity': 'P2', 'title': 'Missing Corti CDI 4 experts', 'description': 'PureLLM no tools'},
    {'gap_id': 'GAP-CP8-03', 'cp': 'CP8', 'agent': 'discharge-summary-structuring', 'severity': 'P3', 'title': 'trace_events only 1 event', 'description': ''},
    {'gap_id': 'GAP-CP8-04', 'cp': 'CP8', 'agent': 'discharge-summary-structuring', 'severity': 'P1', 'title': 'Unified API bypasses structured fields', 'description': 'JSON-in-markdown'},
    {'gap_id': 'GAP-CP8-05', 'cp': 'CP8', 'agent': 'discharge-summary-structuring', 'severity': 'P1', 'title': 'Orchestrator wiring — should be stage 1 sub-agent', 'description': 'Currently standalone'},
    # CP9
    {'gap_id': 'GAP-CP9-01', 'cp': 'CP9', 'agent': 'drg-analyzer', 'severity': 'P2', 'title': 'Repeatability md_len delta 68-628 (run 3 shorter)', 'description': ''},
    {'gap_id': 'GAP-CP9-02', 'cp': 'CP9', 'agent': 'drg-analyzer', 'severity': 'P2', 'title': 'Missing Corti guidelines web-search expert', 'description': ''},
    {'gap_id': 'GAP-CP9-03', 'cp': 'CP9', 'agent': 'drg-analyzer', 'severity': 'P3', 'title': 'trace_events only 1 event', 'description': ''},
    {'gap_id': 'GAP-CP9-04', 'cp': 'CP9', 'agent': 'drg-analyzer', 'severity': 'P1', 'title': 'Unified API bypasses result.risk_points', 'description': 'JSON-in-markdown'},
    {'gap_id': 'GAP-CP9-05', 'cp': 'CP9', 'agent': 'drg-analyzer', 'severity': 'P2', 'title': 'DRG/DIP ruleset hardcoded (should externalize)', 'description': 'Reference Corti compliance {{COMPLIANCE_RULESET}} pattern'},
    {'gap_id': 'GAP-CP9-06', 'cp': 'CP9', 'agent': 'drg-analyzer', 'severity': 'P1', 'title': 'Orchestrator wiring — should be stage 7 sub-agent', 'description': 'Currently standalone'},
]


def write_ux_matrix(path: Path) -> None:
    dims = ['entry_discoverability', 'input_experience', 'output_readability',
            'error_recovery', 'realtime_feedback', 'trace_transparency',
            'cost_transparency', 'copy_download', 'configurable',
            'multi_turn', 'mobile_response', 'i18n']
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['UX dimension'] + [cp for _, cp in AGENT_DIRS] + ['avg'])
        for dim in dims:
            row = [dim]
            total = 0
            for aid, _ in AGENT_DIRS:
                v = UX_SCORES[aid][dim]
                row.append(v)
                total += v
            row.append(round(total / len(AGENT_DIRS), 2))
            w.writerow(row)
        # per-agent avg
        w.writerow(['AGENT_AVERAGE'] + [
            round(sum(UX_SCORES[aid].values()) / 12, 2) for aid, _ in AGENT_DIRS
        ] + [round(sum(sum(u.values()) / 12 for u in UX_SCORES.values()) / 9, 2)])


def write_capability_matrix(path: Path) -> None:
    layers = ['PLATFORM_AVAILABLE', 'AGENT_CONFIGURED', 'RUNTIME_INVOKED',
              'RESULT_CONSUMED', 'QUALITY_VALIDATED', 'TOP_LAYER']
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Capability layer'] + [cp for _, cp in AGENT_DIRS])
        for layer in layers:
            row = [layer]
            for aid, _ in AGENT_DIRS:
                if layer == 'TOP_LAYER':
                    row.append(CAPABILITY[aid]['top'])
                else:
                    row.append(CAPABILITY[aid].get(layer, ''))
            w.writerow(row)


def write_integration_matrix(path: Path) -> None:
    # Collect all integration dim keys
    dims = list(next(iter(INTEGRATION.values())).keys())
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Integration dimension'] + [cp for _, cp in AGENT_DIRS])
        for dim in dims:
            row = [dim]
            for aid, _ in AGENT_DIRS:
                row.append(INTEGRATION[aid].get(dim, ''))
            w.writerow(row)


def write_gap_backlog(path: Path) -> None:
    with path.open('w', encoding='utf-8') as f:
        for g in GAPS:
            f.write(json.dumps(g, ensure_ascii=False) + '\n')


def main() -> int:
    out_root = Path('outputs/phase5_track_b2')
    out_root.mkdir(parents=True, exist_ok=True)

    write_ux_matrix(out_root / 'agent_ux_matrix_b2.csv')
    write_capability_matrix(out_root / 'agent_capability_matrix_b2.csv')
    write_integration_matrix(out_root / 'agent_integration_matrix_b2.csv')
    write_gap_backlog(out_root / 'gap_backlog.jsonl')

    # Summary
    print('=== Phase 5 Track B-2 Phase 11 Aggregator ===')
    print(f'Gaps total: {len(GAPS)}')
    sev_counts = {}
    for g in GAPS:
        sev_counts[g['severity']] = sev_counts.get(g['severity'], 0) + 1
    for sev in sorted(sev_counts.keys()):
        print(f'  {sev}: {sev_counts[sev]}')

    print()
    print('UX averages:')
    for aid, _ in AGENT_DIRS:
        avg = sum(UX_SCORES[aid].values()) / 12
        print(f'  {aid}: {avg:.2f}')
    overall = sum(sum(u.values()) / 12 for u in UX_SCORES.values()) / 9
    print(f'  OVERALL: {overall:.2f}')

    print()
    print('Output files:')
    for f in ['agent_ux_matrix_b2.csv', 'agent_capability_matrix_b2.csv',
              'agent_integration_matrix_b2.csv', 'gap_backlog.jsonl']:
        print(f'  {out_root / f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
