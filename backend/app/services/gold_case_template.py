# Gold Case Template Generator & Validator
import re
from app.schemas.gold_case import GoldCaseCreate

ICD10_PATTERN = re.compile(r"^[A-Z]\d{2}(\.(\d+[xX]?\d*|[xX]\d+))?$")
ICD9_PATTERN = re.compile(r"^\d{2}\.(\d+[xX]?\d*|[xX]\d+)$")
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


def generate_gold_case_template(department: str = "", output_format: str = "json") -> dict:
    """Generate a fillable gold case template for hospital coders.

    Returns a structured template that can be filled in and submitted as a new gold case.
    """
    template = {
        "_instructions": "填写此模板为金标病例。标注字段请根据出院病历填写最准确的编码。",
        "_version": "1.0",
        "case_metadata": {
            "department": department or "<科室名称>",
            "diagnosis_group": "<诊断分组，如'恶性肿瘤化疗'>",
            "specialty": "<专科，如'肿瘤内科'>",
            "difficulty": "medium",
            "risk_tags": [],
            "admission_reason": "<入院原因>",
            "documents": [
                {
                    "doc_type": "主诉",
                    "title": "主诉",
                    "content": "<粘贴病历主诉文本>",
                },
                {
                    "doc_type": "现病史",
                    "title": "现病史",
                    "content": "<粘贴病历现病史文本>",
                },
            ],
        },
        "original_codes": {
            "original_primary_diagnosis": "<原始主要诊断 ICD-10 编码>",
            "original_primary_diag_name": "<原始主要诊断名称>",
            "original_main_procedure": "<原始主要手术 ICD-9-CM-3 编码，如无填 null>",
            "original_main_proc_name": "<原始主要手术名称>",
        },
        "gold_codes": {
            "expected_principal_diagnosis": "<金标准主要诊断 ICD-10>",
            "expected_principal_diag_name": "<金标准主要诊断名称>",
            "expected_principal_procedure": "<金标准主要手术 ICD-9-CM-3，如无填 null>",
            "expected_principal_proc_name": "<金标准主要手术名称>",
            "expected_secondary_diagnoses": ["<其他诊断 ICD-10 编码>"],
            "expected_procedure_codes": ["<其他手术 ICD-9-CM-3 编码>"],
            "expected_drg_group": "<期望 DRG 编码，如 RU14>",
        },
        "acceptable_alternatives": ["<可接受的其他编码>"],
        "reasoning_expectations": ["<AI 应展示的推理能力，如'should cite R013'>"],
        "evidence_spans": [
            {
                "doc_type": "现病史",
                "text": "<支撑编码的病历原文片段>",
                "supports_code": "<片段支持的 ICD 编码>",
            }
        ],
        "known_issues": {
            "missing_codes": [],
            "unsupported_codes": [],
            "documentation_gaps": [],
        },
    }

    if output_format == "markdown":
        return _template_to_markdown(template)
    return template


def _template_to_markdown(template: dict) -> str:
    """Convert template to Markdown format for easy printing/filling."""
    lines = [
        "# Gold Case Template",
        "",
        f"**Version**: {template['_version']}",
        "",
        "## Case Metadata",
        f"- Department: {template['case_metadata']['department']}",
        f"- Diagnosis Group: {template['case_metadata']['diagnosis_group']}",
        f"- Specialty: {template['case_metadata']['specialty']}",
        f"- Difficulty: {template['case_metadata']['difficulty']}",
        f"- Admission Reason: {template['case_metadata']['admission_reason']}",
        "",
        "## Original Codes",
        f"- Original Primary Diagnosis: {template['original_codes']['original_primary_diagnosis']}",
        f"- Original Primary Diag Name: {template['original_codes']['original_primary_diag_name']}",
        f"- Original Main Procedure: {template['original_codes']['original_main_procedure']}",
        "",
        "## Gold Codes (to be filled by expert coder)",
        f"- Expected Principal Diagnosis: {template['gold_codes']['expected_principal_diagnosis']}",
        f"- Expected Principal Procedure: {template['gold_codes']['expected_principal_procedure']}",
        f"- Expected DRG: {template['gold_codes']['expected_drg_group']}",
        "",
        "## Acceptable Alternatives",
        "- " + "\n- ".join(template["acceptable_alternatives"]),
        "",
        "## Reasoning Expectations",
        "- " + "\n- ".join(template["reasoning_expectations"]),
    ]
    return "\n".join(lines)


# ── Validator ────────────────────────────────────────────────────────────────

def _validate_icd10(code: str) -> bool:
    if not code:
        return False
    return bool(ICD10_PATTERN.match(code))


def _validate_icd9(code: str) -> bool:
    if not code:
        return False
    return bool(ICD9_PATTERN.match(code))


def validate_gold_case(data: dict) -> dict:
    """Validate a gold case submission.

    Returns {valid: bool, errors: list[str], warnings: list[str]}.
    """
    errors = []
    warnings = []

    # Required top-level fields
    required = ["case_metadata", "gold_codes"]
    for key in required:
        if key not in data or not data[key]:
            errors.append(f"Missing required section: {key}")
            return {"valid": False, "errors": errors, "warnings": warnings}

    meta = data.get("case_metadata", {})
    gold = data.get("gold_codes", {})

    # Required metadata
    if not meta.get("department"):
        errors.append("case_metadata.department is required")
    if not gold.get("expected_principal_diagnosis"):
        errors.append("gold_codes.expected_principal_diagnosis is required")

    # Validate principal diagnosis format
    pd = gold.get("expected_principal_diagnosis", "")
    if pd and not _validate_icd10(pd):
        warnings.append(f"expected_principal_diagnosis '{pd}' does not match ICD-10 format (e.g. Z51.102)")

    # Validate principal procedure format
    pp = gold.get("expected_principal_procedure", "")
    if pp and pp != "null" and not _validate_icd9(pp):
        warnings.append(f"expected_principal_procedure '{pp}' does not match ICD-9-CM-3 format (e.g. 99.2503)")

    # Validate secondary diagnoses
    secondaries = gold.get("expected_secondary_diagnoses", []) or []
    for i, code in enumerate(secondaries):
        if code and not _validate_icd10(code):
            warnings.append(f"expected_secondary_diagnoses[{i}] '{code}' invalid ICD-10 format")

    # Validate procedure codes
    procs = gold.get("expected_procedure_codes", []) or []
    for i, code in enumerate(procs):
        if code and not _validate_icd9(code):
            warnings.append(f"expected_procedure_codes[{i}] '{code}' invalid ICD-9-CM-3 format")

    # Validate difficulty
    difficulty = meta.get("difficulty", "medium")
    if difficulty not in VALID_DIFFICULTIES:
        warnings.append(f"difficulty '{difficulty}' not in {VALID_DIFFICULTIES}")

    # Check for duplicate codes
    all_codes = [pd] + secondaries
    seen = set()
    for code in all_codes:
        if code and code in seen:
            warnings.append(f"Duplicate code: {code}")
        seen.add(code)

    # Acceptable alternatives format
    alternatives = data.get("acceptable_alternatives", []) or []
    for i, alt in enumerate(alternatives):
        if alt and not _validate_icd10(alt):
            warnings.append(f"acceptable_alternatives[{i}] '{alt}' invalid ICD-10 format")

    valid = len(errors) == 0
    return {"valid": valid, "errors": errors, "warnings": warnings}


def import_gold_case(data: dict) -> dict | None:
    """Validate and convert template data to GoldCaseCreate-compatible dict.

    Returns None if validation fails, otherwise returns dict ready for GoldCaseCreate.
    """
    validation = validate_gold_case(data)
    if not validation["valid"]:
        return None

    meta = data.get("case_metadata", {})
    gold = data.get("gold_codes", {})
    original = data.get("original_codes", {})

    return {
        "department": meta.get("department", ""),
        "diagnosis_group": meta.get("diagnosis_group", ""),
        "difficulty": meta.get("difficulty", "medium"),
        "specialty": meta.get("specialty", ""),
        "risk_tags": meta.get("risk_tags", []),
        "source": "manual",
        "original_primary_diagnosis": original.get("original_primary_diagnosis", ""),
        "original_primary_diag_name": original.get("original_primary_diag_name", ""),
        "original_main_procedure": original.get("original_main_procedure"),
        "original_main_proc_name": original.get("original_main_proc_name"),
        "expected_principal_diagnosis": gold["expected_principal_diagnosis"],
        "expected_principal_diag_name": gold.get("expected_principal_diag_name", ""),
        "expected_principal_procedure": gold.get("expected_principal_procedure"),
        "expected_principal_proc_name": gold.get("expected_principal_proc_name"),
        "expected_secondary_diagnoses": gold.get("expected_secondary_diagnoses", []),
        "expected_procedure_codes": gold.get("expected_procedure_codes", []),
        "expected_drg_group": gold.get("expected_drg_group"),
        "acceptable_alternatives": data.get("acceptable_alternatives", []),
        "reasoning_expectations": data.get("reasoning_expectations", []),
        "evidence_spans": data.get("evidence_spans", []),
        "missing_codes": data.get("known_issues", {}).get("missing_codes", []),
        "unsupported_codes": data.get("known_issues", {}).get("unsupported_codes", []),
        "documentation_gaps": data.get("known_issues", {}).get("documentation_gaps", []),
        "full_case_data": {
            "admission_reason": meta.get("admission_reason", ""),
            "documents": meta.get("documents", []),
        },
    }
