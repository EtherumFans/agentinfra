# iCoDer - search_codes Tool
from app.services.code_dictionary import code_dict_service

async def search_codes_tool(query: str, code_system: str = "ICD10_CN", top_k: int = 10) -> dict:
    """Search medical code dictionary. Tool definition per PRD Section 11.1."""
    results = await code_dict_service.search_codes(query, code_system, top_k)
    return {"results": results}
