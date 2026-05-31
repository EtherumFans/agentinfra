# iCoDer - verify_code_sequence Tool (PRD Section 11.4)
from app.services.code_dictionary import code_dict_service
from app.services.rule_engine import rule_engine_service

async def verify_sequence_tool(
    encounter_id: str,
    diagnosis_codes: list[str],
    procedure_codes: list[str],
    evidence_pack_id: str | None = None,
) -> dict:
    """Verify a complete code sequence for an encounter."""
    results = []
    for code in diagnosis_codes:
        info = await code_dict_service.validate_code(code, "ICD10_CN")
        rule_checks = await rule_engine_service.check_code_against_rules(code, info.get("name", ""), {})
        results.append({
            "code": code,
            "name": info.get("name", "Unknown"),
            "status": "pass" if info["valid"] else "fail",
            "messages": [r["message"] for r in rule_checks],
            "evidence_support": info["valid"],
            "rule_compliance": all(r["status"] == "pass" for r in rule_checks),
        })

    for code in procedure_codes:
        info = await code_dict_service.validate_code(code, "ICD9_CM3")
        rule_checks = await rule_engine_service.check_code_against_rules(code, info.get("name", ""), {})
        results.append({
            "code": code,
            "name": info.get("name", "Unknown"),
            "status": "pass" if info["valid"] else "fail",
            "messages": [r["message"] for r in rule_checks],
            "evidence_support": info["valid"],
            "rule_compliance": all(r["status"] == "pass" for r in rule_checks),
        })

    overall = "pass" if all(r["status"] == "pass" for r in results) else "needs_review"
    return {
        "encounter_id": encounter_id,
        "results": results,
        "overall_status": overall,
        "summary": f"{len(results)} codes checked: {sum(1 for r in results if r['status'] == 'pass')} pass, {sum(1 for r in results if r['status'] != 'pass')} fail/needs review",
    }
