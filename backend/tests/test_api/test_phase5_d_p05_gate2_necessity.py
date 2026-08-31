"""Phase 5 Track D P0.5 Gate 2 — Query Necessity Gate unit tests."""

from __future__ import annotations

from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
)
from app.icoder.agent_runtime.cdi.necessity_gate import (
    apply_necessity_to_case,
    evaluate_case_necessity,
    evaluate_necessity,
)


def _mk_query(qid: str, topic: str, query_text: str = "", gap_id: str = "GAP-1") -> ProviderQuery:
    return ProviderQuery(
        query_id=qid,
        gap_id=gap_id,
        topic=topic,
        reason="r",
        evidence_span=EvidenceSpan(document_id="D", quote="x"),
        query_text=query_text or f"请明确{topic}",
        response_options=["A", "B", "无法确定"],
    )


def _mk_case(queries: list[ProviderQuery], chart: str = "患者咳嗽。") -> CDICase:
    return CDICase(
        case_id="CASE-test",
        chart_excerpt=chart,
        documentation_gaps=[
            DocumentationGap(
                gap_id=q.gap_id,
                description="d",
                why_it_matters="w",
                evidence_span=EvidenceSpan(document_id="D", quote="x"),
            )
            for q in queries
        ],
        proposed_provider_queries=queries,
    )


def test_nq001_chart_already_has_diagnosis_type():
    """Chart says '急性阑尾炎' → query asking for 类型 is unnecessary."""
    q = _mk_query("Q-1", "类型")
    case = _mk_case([q], chart="患者转移性右下腹痛,诊断为急性阑尾炎,手术:腹腔镜阑尾切除术。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    assert result.verdict == "UNNECESSARY"
    assert any("NQ-001" in r for r in result.drop_reasons)


def test_nq001_chart_does_not_answer():
    """Chart says '肺炎' without type → query for 类型 is necessary."""
    q = _mk_query("Q-1", "类型")
    case = _mk_case([q], chart="患者咳嗽发热。胸片:肺炎。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq001_diabetes_type_already_explicit_is_unnecessary() -> None:
    q = _mk_query("Q-type", "糖尿病类型")
    result = evaluate_necessity(
        q,
        chart="入院诊断:2型糖尿病。病程记录存在矛盾。",
        all_queries=[q],
    )

    assert result.verdict == "UNNECESSARY"
    assert any("NQ-001" in reason for reason in result.drop_reasons)


def test_nq002_family_history_only_soft_flag():
    """Family-history-only detail soft-fails but does not drop."""
    q = _mk_query("Q-1", "家族史",
                  query_text="患者父亲有糖尿病史,请明确其父亲所患糖尿病的具体类型")
    case = _mk_case([q], chart="父亲糖尿病。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    # Family-history soft-fails, but no hard fail → still NECESSARY
    assert result.verdict == "NECESSARY"
    assert any("NQ-002" in r for r in result.flag_reasons)


def test_nq004_pathogen_already_cultured():
    """Chart has 痰培养:肺炎链球菌 → query for 病原体 is unnecessary."""
    q = _mk_query("Q-1", "病原体")
    case = _mk_case([q], chart="患者咳嗽。痰培养:肺炎链球菌。")
    result = evaluate_necessity(q, chart=case.chart_excerpt, all_queries=[q])
    assert result.verdict == "UNNECESSARY"
    assert any("NQ-004" in r for r in result.drop_reasons)


def test_nq004_named_acute_suppurative_otitis_drops_generic_severity() -> None:
    q = _mk_query("Q-aom", "急性化脓性中耳炎的严重程度")
    result = evaluate_necessity(
        q,
        chart="诊断：右侧急性化脓性中耳炎。予抗菌治疗。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"
    assert any("NQ-004" in reason for reason in result.drop_reasons)


def test_nq004_resolved_treated_otitis_without_microbiology_drops_pathogen() -> None:
    q = _mk_query("Q-pathogen", "急性化脓性中耳炎病原体")
    chart = "诊断：右侧急性化脓性中耳炎。予抗菌药口服7天，复诊症状缓解。"
    result = evaluate_necessity(q, chart=chart, all_queries=[q])
    assert result.verdict == "UNNECESSARY"


def test_nq004_otitis_with_microbiology_does_not_use_resolved_pathogen_rule() -> None:
    q = _mk_query("Q-pathogen", "急性化脓性中耳炎病原体")
    chart = "诊断：急性化脓性中耳炎。耳分泌物培养检出肺炎链球菌，予抗菌药后好转。"
    result = evaluate_necessity(q, chart=chart, all_queries=[q])
    # The generic pathogen-culture rule may still drop it as already answered;
    # this assertion verifies it is dropped for the explicit culture, not the
    # no-microbiology resolved-otitis rule.
    assert result.verdict == "UNNECESSARY"
    assert any("culture result" in reason for reason in result.drop_reasons)


def test_nq004_haemorrhage_objective_severity_course_and_correlation_drop() -> None:
    chart = "呕血1小时前，BP 95/60，HR 110，Hb 75。胃镜：食管静脉曲张破裂出血。"
    queries = [
        _mk_query("Q-sev", "出血严重程度"),
        _mk_query("Q-course", "出血的病程特点"),
        _mk_query("Q-corr", "血红蛋白与出血的临床关联"),
        _mk_query("Q-etiology", "上消化道出血病因"),
    ]
    verdicts = [
        evaluate_necessity(q, chart=chart, all_queries=queries).verdict
        for q in queries
    ]
    assert verdicts == ["UNNECESSARY", "UNNECESSARY", "UNNECESSARY", "NECESSARY"]


def test_nq004_complete_lipid_panel_drops_derived_labels_but_keeps_etiology() -> None:
    chart = "TC 5.8，LDL-C 3.6，HDL-C 1.0，TG 2.2。10年心血管风险：5%。"
    derived = [
        _mk_query("Q-type", "血脂异常的具体类型"),
        _mk_query("Q-sev", "血脂异常严重程度或风险分层"),
    ]
    etiology = _mk_query("Q-etiology", "血脂异常病因")
    all_queries = [*derived, etiology]
    assert all(
        evaluate_necessity(q, chart=chart, all_queries=all_queries).verdict == "UNNECESSARY"
        for q in derived
    )
    assert evaluate_necessity(
        etiology, chart=chart, all_queries=all_queries,
    ).verdict == "NECESSARY"


def test_nq004_lipid_acute_chronic_course_is_not_a_necessary_query() -> None:
    q = _mk_query("Q-course", "血脂异常的病程")
    chart = "体检发现血脂异常：TC 5.8，LDL-C 3.6，HDL-C 1.0，TG 2.2。"
    result = evaluate_necessity(q, chart=chart, all_queries=[q])
    assert result.verdict == "UNNECESSARY"


def test_nq004_appendicitis_subsite_does_not_change_documentation() -> None:
    q = _mk_query("Q-site", "阑尾的具体解剖部位", "请明确阑尾炎位于阑尾尖端、根部还是全段？")
    result = evaluate_necessity(
        q,
        chart="CT:阑尾肿胀，周围渗出。术后病理:急性单纯性阑尾炎。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_other_disease_site_remains_eligible() -> None:
    q = _mk_query("Q-site", "肺炎具体部位", "请明确肺炎位于哪个肺叶？")
    result = evaluate_necessity(q, chart="胸片提示肺炎。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_acute_otitis_fever_correlation_is_redundant() -> None:
    q = _mk_query("Q-corr", "发热与急性中耳炎的相关性")
    result = evaluate_necessity(
        q, chart="T 38.0℃。诊断:右侧急性化脓性中耳炎。", all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_chronic_cholecystitis_stone_already_answers_type() -> None:
    q = _mk_query("Q-type", "慢性胆囊炎具体类型", "请明确是结石性或非结石性胆囊炎？")
    result = evaluate_necessity(
        q, chart="术后病理:慢性胆囊炎伴胆固醇结石。", all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_type2_diabetes_does_not_need_a_further_subtype() -> None:
    q = _mk_query("Q-type", "2型糖尿病临床亚型", "请明确2型糖尿病的治疗分类或具体亚型？")
    result = evaluate_necessity(q, chart="入院诊断:2型糖尿病。", all_queries=[q])
    assert result.verdict == "UNNECESSARY"


def test_nq004_cross_document_diabetes_specificity_conflict_is_not_redundant() -> None:
    q = _mk_query("Q-type", "糖尿病分型", "请明确出院诊断中的糖尿病分型。")
    result = evaluate_necessity(
        q,
        chart="入院诊断:原发性高血压, 2型糖尿病。出院诊断:高血压, 糖尿病。",
        all_queries=[q],
    )
    assert result.verdict == "NECESSARY"


def test_nq004_consistent_diabetes_type_remains_redundant() -> None:
    q = _mk_query("Q-type", "糖尿病分型", "请明确糖尿病分型。")
    result = evaluate_necessity(
        q,
        chart="入院诊断:2型糖尿病。出院诊断:2型糖尿病。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_diabetes_duration_conflict_remains_eligible() -> None:
    q = _mk_query("Q-duration", "糖尿病病程", "请明确糖尿病是新发还是已有10年？")
    result = evaluate_necessity(
        q,
        chart="入院记录:既往无糖尿病史。出院小结:糖尿病史10年。",
        all_queries=[q],
    )
    assert result.verdict == "NECESSARY"


def test_nq004_complete_hypertension_drops_risk_stratification() -> None:
    q = _mk_query("Q-risk", "高血压危险分层")
    result = evaluate_necessity(
        q,
        chart="诊断:原发性高血压1级(控制良好)，无靶器官损害。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_incomplete_hypertension_keeps_risk_query() -> None:
    q = _mk_query("Q-risk", "高血压危险分层")
    result = evaluate_necessity(q, chart="诊断:高血压。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_primary_hypertension_already_answers_etiology() -> None:
    q = _mk_query("Q-etiology", "高血压病因分类", "请明确高血压是原发性还是继发性？")
    result = evaluate_necessity(
        q, chart="诊断:原发性高血压1级。", all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_unspecified_hypertension_keeps_etiology_query() -> None:
    q = _mk_query("Q-etiology", "高血压病因分类", "请明确高血压是原发性还是继发性？")
    result = evaluate_necessity(q, chart="诊断:高血压。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_low_risk_cough_drops_severity_and_xray_correlation() -> None:
    chart = "咳嗽1周。否认发热、咳脓痰、咯血、胸痛。双肺清晰。胸片:未见活动性病变。"
    queries = [
        _mk_query("Q-severity", "咳嗽严重程度"),
        _mk_query("Q-correlation", "胸片与咳嗽的临床相关性"),
        _mk_query("Q-etiology", "咳嗽病因"),
    ]
    verdicts = [
        evaluate_necessity(q, chart=chart, all_queries=queries).verdict
        for q in queries
    ]
    assert verdicts == ["UNNECESSARY", "UNNECESSARY", "NECESSARY"]


def test_nq004_cough_anatomical_site_is_not_a_valid_symptom_dimension() -> None:
    q = _mk_query("Q-site", "咳嗽的解剖部位", "请明确咳嗽来自上呼吸道还是下呼吸道？")
    result = evaluate_necessity(q, chart="患者咳嗽1周。", all_queries=[q])
    assert result.verdict == "UNNECESSARY"


def test_nq004_explicit_cough_duration_drops_derived_course_class() -> None:
    q = _mk_query("Q-course", "咳嗽病程分类", "请明确咳嗽属于急性、亚急性还是慢性？")
    result = evaluate_necessity(q, chart="患者咳嗽1周。", all_queries=[q])
    assert result.verdict == "UNNECESSARY"


def test_nq004_cough_without_duration_keeps_course_query() -> None:
    q = _mk_query("Q-course", "咳嗽病程分类", "请明确咳嗽属于急性、亚急性还是慢性？")
    result = evaluate_necessity(q, chart="患者咳嗽。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_low_risk_headache_drops_speculative_detail() -> None:
    chart = "间断头痛。否认恶心、呕吐、畏光、畏声、视觉先兆、肢体无力。查体正常。"
    queries = [
        _mk_query("Q-etiology", "头痛病因"),
        _mk_query("Q-severity", "头痛严重程度"),
        _mk_query("Q-course", "头痛病程"),
    ]
    assert all(
        evaluate_necessity(q, chart=chart, all_queries=queries).verdict == "UNNECESSARY"
        for q in queries
    )


def test_nq004_headache_without_red_flag_assessment_keeps_etiology() -> None:
    q = _mk_query("Q-etiology", "头痛病因")
    result = evaluate_necessity(q, chart="突发剧烈头痛，尚未查体。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_explicit_appendicitis_subtype_drops_reclassification() -> None:
    q = _mk_query("Q-type", "急性阑尾炎分型")
    result = evaluate_necessity(
        q, chart="术前诊断:急性阑尾炎(单纯性)。术后病理:急性单纯性阑尾炎。", all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_uncomplicated_chronic_cholecystitis_drops_severity() -> None:
    q = _mk_query("Q-severity", "慢性胆囊炎严重程度或急性程度")
    result = evaluate_necessity(
        q,
        chart="手术顺利，无粘连。术后病理:慢性胆囊炎伴胆固醇结石。术后第2天出院。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_explicit_hypertension_details_are_not_requeried() -> None:
    chart = "高血压10年。诊断:原发性高血压1级(控制良好)，无靶器官损害。"
    queries = [
        _mk_query("Q-course", "高血压病程持续时间"),
        _mk_query("Q-grade", "当前高血压分级依据"),
        _mk_query("Q-organ", "靶器官损害评估范围"),
    ]
    assert all(
        evaluate_necessity(q, chart=chart, all_queries=queries).verdict == "UNNECESSARY"
        for q in queries
    )


def test_nq004_sparse_weight_loss_drops_speculative_refinement() -> None:
    chart = "食欲下降1月，体重减轻5kg。查体无明显异常。建议进一步检查。"
    queries = [
        _mk_query("Q-cause", "食欲下降和体重减轻的病因"),
        _mk_query("Q-severity", "体重减轻严重程度"),
        _mk_query("Q-course", "食欲下降病程特点"),
    ]
    assert all(
        evaluate_necessity(q, chart=chart, all_queries=queries).verdict == "UNNECESSARY"
        for q in queries
    )


def test_nq004_redaction_placeholder_is_not_a_provider_query() -> None:
    q = _mk_query(
        "Q-redacted", "检查结果解读",
        "请明确'<REDACTED:NAME>常'所指的具体检查项目及结果。",
    )
    q.evidence_span = EvidenceSpan(document_id="D", quote="<REDACTED:NAME>常")
    result = evaluate_necessity(
        q,
        chart="间断胸闷。<REDACTED:NAME>常。建议随访。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_normal_named_test_remains_eligible() -> None:
    q = _mk_query("Q-test", "检查结果解读", "请明确异常心电图的具体结果。")
    q.evidence_span = EvidenceSpan(document_id="D", quote="心电图异常")
    result = evaluate_necessity(q, chart="心电图异常。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_truncated_normal_exam_token_is_not_query_evidence() -> None:
    q = _mk_query("Q-exam", "体格检查发现", "请补充该处体格检查发现的完整描述。")
    q.evidence_span = EvidenceSpan(document_id="D", quote="常")
    result = evaluate_necessity(
        q, chart="间断胸闷。<REDACTED:NAME>常。建议随访。", all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_followup_schedule_is_not_a_diagnosis_gap() -> None:
    q = _mk_query("Q-followup", "随访计划", "请明确随访的具体安排和时间。")
    q.evidence_span = EvidenceSpan(document_id="D", quote="建议随访")
    result = evaluate_necessity(q, chart="间断胸闷。建议随访。", all_queries=[q])
    assert result.verdict == "UNNECESSARY"


def test_nq004_missing_diagnostic_followup_result_remains_eligible() -> None:
    q = _mk_query("Q-result", "病理结果", "请明确随访病理检查的最终结果。")
    q.evidence_span = EvidenceSpan(document_id="D", quote="病理结果待回报")
    result = evaluate_necessity(q, chart="病理结果待回报。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_confirmed_weight_loss_diagnosis_keeps_real_gap() -> None:
    q = _mk_query("Q-type", "恶性肿瘤病理类型")
    result = evaluate_necessity(
        q, chart="体重减轻5kg。诊断:胃恶性肿瘤，病理类型待定。", all_queries=[q],
    )
    assert result.verdict == "NECESSARY"


def test_nq004_nihss_drops_redundant_stroke_severity_label() -> None:
    q = _mk_query("Q-severity", "脑梗死严重程度分级")
    result = evaluate_necessity(
        q, chart="NIHSS 8。入院诊断:脑梗死。", all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_stroke_without_nihss_keeps_severity_query() -> None:
    q = _mk_query("Q-severity", "脑梗死严重程度分级")
    result = evaluate_necessity(q, chart="入院诊断:脑梗死。", all_queries=[q])
    assert result.verdict == "NECESSARY"


def test_nq004_explicit_poor_glycemic_control_drops_remeasurement_query() -> None:
    q = _mk_query("Q-control", "Glycemic control severity", "Please provide HbA1c to classify glycemic control severity.")
    result = evaluate_necessity(
        q, chart="出院小结:糖尿病史10年，平素血糖控制不佳。", all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq001_acute_mi_does_not_answer_stemi_or_killip_specificity() -> None:
    chart = "心电图:前壁导联ST段抬高。入院诊断:急性心肌梗死。"
    queries = [
        _mk_query("Q-type", "急性心肌梗死类型和部位"),
        _mk_query("Q-severity", "心肌梗死Killip分级"),
    ]
    assert all(
        evaluate_necessity(q, chart=chart, all_queries=queries).verdict == "NECESSARY"
        for q in queries
    )


def test_nq004_copd_blood_gas_interpretation_is_derived() -> None:
    q = _mk_query("Q-abg", "Clinical correlation of blood gas", "请解释血气的酸碱失衡和氧合状态。")
    result = evaluate_necessity(
        q,
        chart="入院诊断:慢阻肺急性加重。血气:pH 7.34, PaCO2 62, PaO2 55。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_qualitative_positive_lab_drops_exact_value_backfill() -> None:
    q = _mk_query(
        "Q-lab-value",
        "肌钙蛋白I的具体数值及参考范围",
        "肌钙蛋白I的具体数值及参考范围是？",
    )
    result = evaluate_necessity(
        q,
        chart="心电图:前壁导联ST段抬高。肌钙蛋白I升高。入院诊断:急性心肌梗死。",
        all_queries=[q],
    )
    assert result.verdict == "UNNECESSARY"


def test_nq004_aecopd_prioritizes_respiratory_failure_over_generic_refinements() -> None:
    chart = "入院诊断:慢阻肺急性加重。血气:pH 7.34, PaCO2 62, PaO2 55。"
    severity = _mk_query("Q-severity", "COPD exacerbation severity", "该患者慢阻肺急性加重的严重程度如何评估？")
    etiology = _mk_query("Q-etiology", "COPD exacerbation etiology", "该患者本次慢阻肺急性加重的可能诱因是什么？")
    respiratory_failure = _mk_query("Q-rf", "Respiratory failure type", "血气结果提示的呼吸衰竭类型是什么？")
    assert evaluate_necessity(severity, chart=chart, all_queries=[severity]).verdict == "UNNECESSARY"
    assert evaluate_necessity(etiology, chart=chart, all_queries=[etiology]).verdict == "UNNECESSARY"
    assert evaluate_necessity(
        respiratory_failure, chart=chart, all_queries=[respiratory_failure]
    ).verdict == "NECESSARY"


def test_nq004_ami_drops_speculative_etiology_but_keeps_type_and_site() -> None:
    chart = (
        "心电图:前壁导联ST段抬高。肌钙蛋白I升高。"
        "冠脉造影:前降支近段100%闭塞。行PCI。入院诊断:急性心肌梗死。"
    )
    etiology = _mk_query("Q-cause", "心肌梗死的病因", "该心肌梗死的病因是？")
    specificity = _mk_query("Q-type", "急性心肌梗死类型和部位", "请明确心肌梗死类型和部位。")
    assert evaluate_necessity(etiology, chart=chart, all_queries=[etiology]).verdict == "UNNECESSARY"
    assert evaluate_necessity(
        specificity, chart=chart, all_queries=[specificity]
    ).verdict == "NECESSARY"


def test_nq004_explicit_weight_loss_amount_duration_and_workup_plan_are_not_cdi_gaps() -> None:
    chart = "食欲下降1月，体重减轻5kg。查体无明显异常。建议进一步检查。"
    weight = _mk_query(
        "Q-weight", "体重减轻的程度和持续时间", "请描述体重减轻的具体情况。"
    )
    workup = _mk_query(
        "Q-workup", "进一步检查的具体项目或计划", "建议进行哪些具体检查？"
    )
    assert evaluate_necessity(weight, chart=chart, all_queries=[weight]).verdict == "UNNECESSARY"
    assert evaluate_necessity(workup, chart=chart, all_queries=[workup]).verdict == "UNNECESSARY"


def test_nq004_aecopd_severity_conflict_is_not_suppressed_by_abg_rule() -> None:
    chart = (
        "入院诊断:COPD急性加重，重度。血气:pH 7.38, PaCO2 56, PaO2 70。"
        "病程记录:COPD急性加重，轻度。出院诊断:COPD急性加重，中度。"
    )
    query = _mk_query(
        "Q-conflict-severity",
        "COPD急性加重严重程度",
        "请明确本次COPD急性加重的最终严重程度分级。",
    )
    assert evaluate_necessity(query, chart=chart, all_queries=[query]).verdict == "NECESSARY"


def test_nq004_pneumonia_secondary_location_and_lab_correlation_are_suppressed() -> None:
    chart = "胸片示右下肺浸润影。WBC 14.5，T 38.3℃。入院诊断:肺炎。"
    location = _mk_query("Q-location", "肺炎的解剖部位", "请明确肺炎的具体肺叶或肺段。")
    correlation = _mk_query("Q-correlation", "实验室异常与肺炎的临床相关性", "请说明WBC升高与肺炎的相关性。")
    assert evaluate_necessity(location, chart=chart, all_queries=[location]).verdict == "UNNECESSARY"
    assert evaluate_necessity(correlation, chart=chart, all_queries=[correlation]).verdict == "UNNECESSARY"


def test_nq004_dka_generic_acidosis_plan_is_suppressed_for_diagnosis_focus() -> None:
    query = _mk_query(
        "Q-acidosis", "代谢性酸中毒的病因评估",
        "请明确代谢性酸中毒的病因及后续诊疗计划。",
    )
    chart = "FPG 12.5, pH 7.30, HCO3 16, 酮体阳性。入院诊断:2型糖尿病。"
    assert evaluate_necessity(query, chart=chart, all_queries=[query]).verdict == "UNNECESSARY"


def test_nq004_sparse_weight_loss_does_not_invite_differential_guessing() -> None:
    query = _mk_query(
        "Q-differential", "诊断或鉴别诊断",
        "患者食欲下降和体重减轻，可能的诊断或鉴别诊断是什么？",
    )
    chart = "食欲下降1月，体重减轻5kg。查体无明显异常。建议进一步检查。"
    assert evaluate_necessity(query, chart=chart, all_queries=[query]).verdict == "UNNECESSARY"


def test_nq004_isolated_wbc_interpretation_and_plan_is_not_cdi_query() -> None:
    query = _mk_query(
        "Q-wbc-plan", "WBC升高的临床意义及处理计划",
        "针对WBC 14.5这一异常结果，临床上的解读和计划是什么？",
    )
    chart = "WBC 14.5，T 38.3℃。入院诊断:肺炎。"
    assert evaluate_necessity(query, chart=chart, all_queries=[query]).verdict == "UNNECESSARY"


def test_nq004_ami_secondary_procedure_and_nonculprit_details_are_suppressed() -> None:
    chart = "冠脉造影:前降支近段100%闭塞。行PCI。入院诊断:急性心肌梗死。"
    vessel = _mk_query("Q-vessels", "冠脉病变的血管名称", "请明确其他冠脉血管的病变情况。")
    procedure = _mk_query("Q-pci", "PCI的具体操作细节", "本次PCI的具体操作细节是什么？")
    assert evaluate_necessity(vessel, chart=chart, all_queries=[vessel]).verdict == "UNNECESSARY"
    assert evaluate_necessity(procedure, chart=chart, all_queries=[procedure]).verdict == "UNNECESSARY"


def test_nq004_ami_explicit_onset_and_unsupported_vessel_count_are_suppressed() -> None:
    chart = (
        "持续胸痛2小时。冠脉造影:前降支近段100%闭塞。"
        "行PCI。入院诊断:急性心肌梗死。"
    )
    onset = _mk_query("Q-onset", "心肌梗死发病时间", "请明确心肌梗死发病时间。")
    count = _mk_query("Q-count", "冠脉病变血管数量", "请明确冠脉病变血管数量。")
    assert evaluate_necessity(onset, chart=chart, all_queries=[onset]).verdict == "UNNECESSARY"
    assert evaluate_necessity(count, chart=chart, all_queries=[count]).verdict == "UNNECESSARY"


def test_nq004_low_risk_cough_keeps_cause_but_drops_history_only_hypertension_refinement() -> None:
    chart = (
        "咳嗽1周。否认发热、咳脓痰、咯血、胸痛。既往:高血压。"
        "查体:双肺清晰。胸片:未见活动性病变。"
    )
    cough = _mk_query("Q-cough-cause", "咳嗽的病因", "咳嗽的可能病因是什么？")
    hypertension = _mk_query("Q-htn-control", "高血压的严重程度和当前控制情况", "请描述高血压严重程度及控制情况。")
    assert evaluate_necessity(cough, chart=chart, all_queries=[cough]).verdict == "NECESSARY"
    assert evaluate_necessity(hypertension, chart=chart, all_queries=[hypertension]).verdict == "UNNECESSARY"


def test_nq004_clean_evidence_can_support_query_with_secondary_redacted_span() -> None:
    q = _mk_query("Q-conflict", "糖尿病分型", "请明确出院诊断中的糖尿病分型。")
    q.evidence_spans = [
        EvidenceSpan(document_id="admission", quote="2型糖尿病"),
        EvidenceSpan(document_id="discharge", quote="出院诊断:<REDACTED:NAME>, 糖尿病"),
    ]
    result = evaluate_necessity(
        q,
        chart="入院诊断:2型糖尿病。出院诊断:<REDACTED:NAME>, 糖尿病。",
        all_queries=[q],
    )
    assert result.verdict == "NECESSARY"


def test_nq005_redundant_topic_dropped():
    """Two queries with same topic — second one is redundant."""
    q1 = _mk_query("Q-1", "部位")
    q2 = _mk_query("Q-2", "部位")
    case = _mk_case([q1, q2], chart="x")
    r1 = evaluate_necessity(q1, chart=case.chart_excerpt, all_queries=[q1, q2])
    r2 = evaluate_necessity(q2, chart=case.chart_excerpt, all_queries=[q1, q2])
    # Exactly one should hard-fail NQ-005
    assert (r1.verdict == "UNNECESSARY") != (r2.verdict == "UNNECESSARY")


def test_overquery_guard_triggers_at_5_queries():
    """Case with ≥5 queries triggers NQ-006."""
    queries = [_mk_query(f"Q-{i}", f"topic-{i}") for i in range(1, 6)]
    case = _mk_case(queries, chart="x")
    result = evaluate_case_necessity(case)
    assert result.overquery_triggered is True
    assert result.overquery_count == 5


def test_overquery_guard_does_not_trigger_at_4():
    """Case with exactly 4 queries does NOT trigger NQ-006 (threshold = >4)."""
    queries = [_mk_query(f"Q-{i}", f"topic-{i}") for i in range(1, 5)]
    case = _mk_case(queries, chart="x")
    result = evaluate_case_necessity(case)
    assert result.overquery_triggered is False


def test_apply_necessity_drops_unnecessary():
    """apply_necessity_to_case mutates the case — drops UNNECESSARY queries."""
    q1 = _mk_query("Q-1", "类型")  # unnecessary (chart has 急性阑尾炎)
    q2 = _mk_query("Q-2", "部位")  # necessary (chart doesn't specify)
    case = _mk_case([q1, q2], chart="患者诊断为急性阑尾炎。")
    result = apply_necessity_to_case(case)
    assert len(case.proposed_provider_queries) == 1
    assert case.proposed_provider_queries[0].query_id == "Q-2"
    assert "Q-1" in result.per_query
    assert result.per_query["Q-1"].verdict == "UNNECESSARY"
    assert len(case.query_rewrite_queue) == 1
    rejected = case.query_rewrite_queue[0]
    assert rejected["query_id"] == "Q-1"
    assert rejected["gap_id"] == "GAP-1"
    assert rejected["status"] == "REJECTED_AS_UNNECESSARY"
    assert rejected["gate_reasons"]
    assert rejected["evidence_spans"][0]["quote"] == "x"


def test_apply_necessity_preserves_all_when_necessary():
    """All queries necessary → none dropped."""
    queries = [
        _mk_query("Q-1", "类型"),
        _mk_query("Q-2", "部位"),
    ]
    case = _mk_case(queries, chart="患者咳嗽。诊断肺炎。")
    apply_necessity_to_case(case)
    assert len(case.proposed_provider_queries) == 2
    assert case.query_rewrite_queue == []
