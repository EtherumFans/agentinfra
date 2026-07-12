"""Track H1.1 — Build mechanism probe cases.

Per PDF §6, the controlled-probe methodology uses 8 minimal-pair groups + 1 expert routing
probe + 1 repeatability probe. Each minimal pair consists of A (test) and B (control) — the
only difference being the variable under test.

Categories per PDF §6.2:
- NEGATION (red flag denied vs absent)
- HISTORY (past condition in history vs active problem)
- FAMILY_HISTORY (family history vs patient history)
- SUSPECTED ('suspected'/'possible' vs confirmed)
- COMPLETE_CHART (over-query probe — already complete vs gap)
- CONTRADICTION (doc A vs doc B conflict)
- EVIDENCE_STRENGTH (strong evidence vs weak evidence)
- QUERY_CARDINALITY (1 expected vs 3 expected)

Plus:
- EXPERT_ROUTING (4 cases — one per Expert: coding/web/pubmed/calculator)
- REPEATABILITY (5 cases selected from above, to be run 3× each)

Cases are English-only (Corti constraint) with explicit chart text, expected ranges, and
the variable under test.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("tests/fixtures/track_h_mechanism_probes.json")
OUT.parent.mkdir(parents=True, exist_ok=True)


def case(
    case_id: str,
    group: str,
    variant: str,
    chart_en: str,
    chart_zh: str,
    expected_query_min: int,
    expected_query_max: int,
    variable_under_test: str,
    expected_topics: list[str] | None = None,
    forbidden_topics: list[str] | None = None,
    notes: str = "",
) -> dict:
    return {
        "case_id": case_id,
        "group": group,
        "variant": variant,  # A / B / C / D
        "chart_en": chart_en,
        "chart_zh": chart_zh,
        "expected": {
            "query_count_min": expected_query_min,
            "query_count_max": expected_query_max,
            "expected_query_topics": expected_topics or [],
            "forbidden_query_topics": forbidden_topics or [],
            "no_query_expected": expected_query_max == 0,
        },
        "variable_under_test": variable_under_test,
        "notes": notes,
    }


CASES = [
    # === NEGATION ===
    case(
        "H-NEG-A-001",
        "NEGATION",
        "A",
        "42-year-old female with intermittent headache for 2 weeks. Denies nausea, vomiting, photophobia, phonophobia, visual aura, limb weakness, neck stiffness. No history of migraine. No family history of CNS disease. Normal neurological exam. Normal vital signs.",
        "42岁女性，间歇性头痛2周。否认恶心、呕吐、畏光、畏声、视觉先兆、肢体无力、颈项强直。无偏头痛史。无家族CNS疾病史。神经查体正常。生命体征正常。",
        0, 0,
        "denied_symptoms",
        expected_topics=[],
        forbidden_topics=["migraine", "intracranial lesion", "CNS tumor", "meningitis"],
        notes="All red flags denied — should NOT generate any query",
    ),
    case(
        "H-NEG-B-001",
        "NEGATION",
        "B",
        "42-year-old female with intermittent headache for 2 weeks. Patient reports photophobia and mild nausea. Symptoms worse in the evening. No prior workup.",
        "42岁女性，间歇性头痛2周。患者诉畏光、轻度恶心。傍晚加重。既往未检查。",
        1, 2,
        "denied_symptoms",
        expected_topics=["headache characterization", "migraine features"],
        forbidden_topics=[],
        notes="Some red flags present — query about features is reasonable",
    ),

    # === HISTORY ===
    case(
        "H-HIST-A-002",
        "HISTORY",
        "A",
        "68-year-old male admitted for elective hip replacement. History of type 2 diabetes mellitus (well-controlled on metformin), hypertension, and hyperlipidemia. Postoperative course unremarkable. Discharged on post-op day 3.",
        "68岁男性，择期髋关节置换术入院。既往2型糖尿病（二甲双胍控制良好）、高血压、高脂血症。术后平稳。术后第3天出院。",
        0, 1,
        "history_vs_active",
        expected_topics=[],
        forbidden_topics=["diabetes complication"],
        notes="History of diabetes is documented as controlled — query about active diabetes complications would be over-query",
    ),
    case(
        "H-HIST-B-002",
        "HISTORY",
        "B",
        "68-year-old male admitted for elective hip replacement. History of type 2 diabetes on metformin. Post-op day 2: blood glucose 285 mg/dL, requires insulin sliding scale. HbA1c 9.8%. Wound site shows delayed healing.",
        "68岁男性，择期髋关节置换术入院。既往2型糖尿病（二甲双胍）。术后第2天：血糖285 mg/dL，需胰岛素滑动刻度。HbA1c 9.8%。伤口愈合延迟。",
        1, 2,
        "history_vs_active",
        expected_topics=["diabetes control/complication", "wound healing"],
        forbidden_topics=[],
        notes="Active diabetes complication (poor control + wound healing) — query REQUIRED",
    ),

    # === FAMILY_HISTORY ===
    case(
        "H-FH-A-003",
        "FAMILY_HISTORY",
        "A",
        "55-year-old female with breast cancer in her mother and maternal aunt. Patient herself has no breast symptoms, normal mammogram 3 months ago, normal breast exam today. No other complaints.",
        "55岁女性，母亲和姨妈患乳腺癌。患者本人无乳腺症状，3个月前乳腺X线正常，今日乳腺查体正常。无其他主诉。",
        0, 0,
        "family_vs_personal",
        expected_topics=[],
        forbidden_topics=["breast cancer", "BRCA testing"],
        notes="Family history only — patient does not have the condition; querying would be inappropriate",
    ),
    case(
        "H-FH-B-003",
        "FAMILY_HISTORY",
        "B",
        "55-year-old female with palpable right breast mass found on self-exam 1 week ago. Family history of breast cancer (mother). Mammogram pending. Ultrasound shows 2.1 cm irregular mass at 2 o'clock position.",
        "55岁女性，自检发现右乳包块1周。家族乳腺癌史（母亲）。乳腺X线待查。超声示2点位不规则包块2.1 cm。",
        1, 2,
        "family_vs_personal",
        expected_topics=["breast mass characterization", "BI-RADS / pathology correlation"],
        forbidden_topics=[],
        notes="Patient has active finding + family history — query on characterization is reasonable",
    ),

    # === SUSPECTED ===
    case(
        "H-SUS-A-004",
        "SUSPECTED",
        "A",
        "Patient admitted with 'possible pneumonia' per ED note. Chart review: clear lung fields on auscultation, no cough, no fever, normal WBC, chest X-ray clear. No antibiotic therapy started.",
        "患者入院诊断ED记录为'可能肺炎'。病历查阅：听诊双肺清晰，无咳嗽，无发热，WBC正常，胸片清晰。未启用抗生素。",
        0, 1,
        "suspected_vs_confirmed",
        expected_topics=["reconcile 'possible pneumonia' with objective findings"],
        forbidden_topics=[],
        notes="Documented as 'possible' but no supporting evidence — query about reconciliation",
    ),
    case(
        "H-SUS-B-004",
        "SUSPECTED",
        "B",
        "Patient admitted with 'possible pneumonia'. Chart review: febrile 38.8°C, crackles in right lower lobe, productive cough with yellow sputum, WBC 16.5 with left shift, chest X-ray shows RLL infiltrate. Started on ceftriaxone + azithromycin.",
        "患者入院诊断'可能肺炎'。病历查阅：发热38.8°C，右下肺湿啰音，咳黄痰，WBC 16.5伴左移，胸片右下肺浸润。已启用头孢曲松+阿奇霉素。",
        1, 2,
        "suspected_vs_confirmed",
        expected_topics=["pneumonia type (CAP vs HAP)", "pneumonia severity"],
        forbidden_topics=[],
        notes="'Possible' but objective findings confirm — query about specificity (type/severity)",
    ),

    # === COMPLETE_CHART ===
    case(
        "H-CMP-A-005",
        "COMPLETE_CHART",
        "A",
        "45-year-old male with migrating right lower quadrant pain for 1 day. McBurney point tenderness and rebound positive. WBC 13.2, neutrophils 85%. CT: swollen appendix with surrounding exudate, no perforation. Pre-op diagnosis: acute appendicitis (simple, no perforation). Underwent laparoscopic appendectomy. Pathology: acute simple appendicitis. No complications. Recovered well, discharged on day 3.",
        "45岁男性，转移性右下腹痛1天。McBurney点压痛反跳痛阳性。WBC 13.2，中性85%。CT:阑尾肿胀伴周围渗出，无穿孔。术前诊断:急性阑尾炎（单纯性，无穿孔）。行腹腔镜阑尾切除术。病理:急性单纯性阑尾炎。无并发症。恢复良好，第3天出院。",
        0, 0,
        "complete_chart_overquery",
        expected_topics=[],
        forbidden_topics=["peritoneal involvement", "gangrene", "pain duration"],
        notes="Already-complete chart — query would be over-query (this is the COMPLETE-011 case)",
    ),

    # === CONTRADICTION ===
    case(
        "H-CTR-A-006",
        "CONTRADICTION",
        "A",
        "ED note: 'Patient with left wrist fracture after fall, splint applied.' Orthopedic note (same day): 'Right wrist fracture, cast applied.' Radiology report: 'Linear fracture distal radius, side not specified.' Patient reports pain on right wrist.",
        "ED记录：'患者左腕骨折后跌倒，已夹板固定。'骨科记录（同日）：'右腕骨折，已石膏固定。'放射科报告：'桡骨远端线性骨折，侧别未指定。'患者诉右腕疼痛。",
        1, 2,
        "doc_contradiction",
        expected_topics=["fracture laterality reconciliation"],
        forbidden_topics=[],
        notes="A vs B laterality conflict — query REQUIRED",
    ),
    case(
        "H-CTR-B-006",
        "CONTRADICTION",
        "B",
        "ED note: 'Patient with left wrist fracture after fall.' Orthopedic note: 'Left wrist fracture confirmed, cast applied.' Radiology: 'Left distal radius fracture.' Patient reports left wrist pain. Consistent across all notes.",
        "ED记录：'左腕骨折后跌倒。'骨科记录：'左腕骨折确认，已石膏固定。'放射科：'左桡骨远端骨折。'患者诉左腕疼痛。所有记录一致。",
        0, 0,
        "doc_contradiction",
        expected_topics=[],
        forbidden_topics=[],
        notes="No contradiction — no query needed",
    ),

    # === EVIDENCE_STRENGTH ===
    case(
        "H-EVS-A-007",
        "EVIDENCE_STRENGTH",
        "A",
        "Patient with single creatinine of 1.4 mg/dL (baseline 1.0). No urine output records. No other renal markers. Normal CBC. No comorbidities suggesting CKD.",
        "患者单次肌酐1.4 mg/dL（基线1.0）。无尿量记录。无其他肾脏标志物。CBC正常。无CKD相关合并症。",
        0, 1,
        "evidence_strength",
        expected_topics=[],
        forbidden_topics=["AKI stage", "CKD"],
        notes="Single weak evidence — querying AKI stage would be over-query",
    ),
    case(
        "H-EVS-B-007",
        "EVIDENCE_STRENGTH",
        "B",
        "Patient with creatinine 2.8 mg/dL (baseline 0.9), BUN 65, K+ 5.6, urine output 0.3 mL/kg/h × 8 hours, no dialysis yet. Renal consult placed. CKD-EPI eGFR 22.",
        "患者肌酐2.8 mg/dL（基线0.9），BUN 65，K+ 5.6，尿量0.3 mL/kg/h ×8小时，尚未透析。肾内科会诊。CKD-EPI eGFR 22。",
        1, 2,
        "evidence_strength",
        expected_topics=["AKI etiology", "AKI stage"],
        forbidden_topics=[],
        notes="Strong multi-source evidence — query REQUIRED",
    ),

    # === QUERY_CARDINALITY ===
    case(
        "H-CAR-A-008",
        "QUERY_CARDINALITY",
        "A",
        "Patient with Community-acquired pneumonia. CURB-65 not documented. CAP vs HAP not specified. Severity not classified. No culture results documented.",
        "社区获得性肺炎患者。CURB-65未记录。CAP vs HAP未明确。严重程度未分级。未记录培养结果。",
        1, 2,
        "cardinality",
        expected_topics=["pneumonia severity (CURB-65/PSI)", "CAP vs HAP"],
        forbidden_topics=[],
        notes="2 expected cardinality",
    ),
    case(
        "H-CAR-B-008",
        "QUERY_CARDINALITY",
        "B",
        "Patient with CAP and 3 specific documentation gaps: (1) severity score (CURB-65/PSI) not documented, (2) type of pneumonia (CAP vs HAP) not specified, (3) causative organism not identified despite sputum culture ordered, (4) oxygenation status not documented despite SpO2 88%.",
        "CAP患者，3处具体文档缺口:（1）严重程度评分（CURB-65/PSI）未记录，（2）肺炎类型（CAP vs HAP）未明确，（3）已送痰培养但未明确病原体，（4）SpO2 88%但氧合状态未记录。",
        2, 4,
        "cardinality",
        expected_topics=["severity", "type", "organism", "oxygenation"],
        forbidden_topics=[],
        notes="4 expected cardinality",
    ),

    # === EXPERT_ROUTING (§6.3) ===
    case(
        "H-EXP-COD-009",
        "EXPERT_ROUTING",
        "CODING",
        "Patient with acute myocardial infarction. Cardiology note says 'NSTEMI'. Troponin peaked at 4.2. No ICD coding documented in chart.",
        "急性心肌梗死患者。心内科记录'NSTEMI'。肌钙蛋白峰值4.2。病历中无ICD编码记录。",
        1, 2,
        "trigger_coding_expert",
        expected_topics=["MI type documentation (NSTEMI vs STEMI)", "ICD-10-CM specificity"],
        forbidden_topics=[],
        notes="Should trigger coding-expert (ICD coding-relevant gap)",
    ),
    case(
        "H-EXP-PUB-010",
        "EXPERT_ROUTING",
        "PUBMED",
        "Patient with rare autoimmune encephalitis. Diagnosis of 'anti-NMDA receptor encephalitis' documented but clinical criteria not listed in chart. No antibody titer documented.",
        "罕见自身免疫性脑炎患者。诊断'抗NMDA受体脑炎'已记录但临床标准未列出。未记录抗体滴度。",
        1, 2,
        "trigger_pubmed_expert",
        expected_topics=["clinical diagnostic criteria for anti-NMDA receptor encephalitis"],
        forbidden_topics=[],
        notes="Should trigger pubmed-expert (rare disease, clinical criteria unclear)",
    ),
    case(
        "H-EXP-WEB-011",
        "EXPERT_ROUTING",
        "WEB_SEARCH",
        "Patient on long-term amiodarone with new-onset pulmonary toxicity suspected. Need current guideline on amiodarone pulmonary toxicity screening protocol. No recent guideline referenced in chart.",
        "患者长期胺碘酮治疗，疑新发肺毒性。需要胺碘酮肺毒性筛查流程的最新指南。病历中无近期指南参考。",
        1, 2,
        "trigger_web_search_expert",
        expected_topics=["current guideline on amiodarone pulmonary toxicity screening"],
        forbidden_topics=[],
        notes="Should trigger web-search-expert (current guideline needed)",
    ),
    case(
        "H-EXP-CALC-012",
        "EXPERT_ROUTING",
        "CALCULATOR",
        "Patient with atrial fibrillation, CHA2DS2-VASc score components present: hypertension, diabetes, age 75, female, prior TIA. Score not calculated in chart. On warfarin with INR 1.8 (subtherapeutic).",
        "房颤患者，CHA2DS2-VASc评分组分齐全:高血压、糖尿病、75岁、女性、既往TIA。病历中未计算评分。华法林治疗中INR 1.8（低于治疗窗）。",
        1, 2,
        "trigger_calculator_expert",
        expected_topics=["CHA2DS2-VASc score", "anticoagulation adequacy"],
        forbidden_topics=[],
        notes="Should trigger calculator-expert (score calculation needed)",
    ),

    # === REPEATABILITY (§6.4 — subset of above, to run 3× each) ===
    # Selected 5 cases spanning different probe groups, expected stable outputs
    # These IDs reference the cases above (don't introduce new chart text)
    # The repeatability runner re-sends the same chart text 3 times.
]


def main() -> None:
    repeatability_subset = [
        {"case_id": "H-NEG-A-001", "reason": "NO_QUERY baseline — variance should be 0"},
        {"case_id": "H-CMP-A-005", "reason": "Complete chart — variance measures over-query flakiness"},
        {"case_id": "H-CTR-A-006", "reason": "Contradiction case — variance measures gap detection stability"},
        {"case_id": "H-EXP-COD-009", "reason": "Coding-expert trigger — variance measures routing stability"},
        {"case_id": "H-EVS-B-007", "reason": "Strong evidence — variance measures query count stability"},
    ]

    output = {
        "_meta": {
            "source": "Track H1.1 — Mechanism Probe Cases (PDF §6)",
            "version": "1.0",
            "case_count": len(CASES),
            "groups": list({c["group"] for c in CASES}),
            "repeatability_subset": repeatability_subset,
            "usage": (
                "Used by 04_run_minimal_pair_probes.py, 05_run_expert_routing_probes.py, "
                "06_run_repeatability_probes.py"
            ),
        },
        "cases": CASES,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # Print summary
    print(f"Wrote: {OUT}")
    print(f"Total cases: {len(CASES)}")
    print()
    by_group: dict[str, int] = {}
    for c in CASES:
        by_group[c["group"]] = by_group.get(c["group"], 0) + 1
    print("By group:")
    for g, n in sorted(by_group.items()):
        print(f"  {g:25s} {n}")
    print()
    print(f"Repeatability subset: {len(repeatability_subset)} cases × 3 runs = {len(repeatability_subset) * 3} executions")


if __name__ == "__main__":
    main()
