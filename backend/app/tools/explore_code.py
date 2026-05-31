# iCoDer - explore_code Tool (PRD Section 11.2)
from app.services.code_dictionary import code_dict_service

async def explore_code_tool(code: str, code_system: str = "ICD10_CN") -> dict:
    """Explore code hierarchy, includes/excludes, parent/child relationships."""
    result = await code_dict_service.explore_code(code, code_system)
    if result is None:
        return {"error": f"Code '{code}' not found in {code_system}"}
    return result
