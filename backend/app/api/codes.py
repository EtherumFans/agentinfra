# iCoDer - Codes API Router
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.codes import (
    CodeSearchRequest, CodeSearchResponse, CodeExploreRequest,
    CodeExploreResponse, RuleRetrieveRequest, RuleRetrieveResponse,
    CodeVerifyRequest, CodeVerifyResponse,
)
from app.middleware.auth import get_current_user
from app.services.code_dictionary import code_dict_service
from app.services.rule_engine import rule_engine_service
from app.tools.search_codes import search_codes_tool
from app.tools.explore_code import explore_code_tool
from app.tools.retrieve_rules import retrieve_rules_tool
from app.tools.verify_sequence import verify_sequence_tool

router = APIRouter(prefix="/api/codes", tags=["codes"])


@router.post("/search", response_model=CodeSearchResponse)
async def search_codes(
    data: CodeSearchRequest,
    current_user: User = Depends(get_current_user),
):
    result = await search_codes_tool(data.query, data.code_system, data.top_k)
    return CodeSearchResponse(
        results=result["results"],
        query=data.query,
        code_system=data.code_system,
        total_found=len(result["results"]),
    )


@router.post("/explore", response_model=CodeExploreResponse)
async def explore_code(
    data: CodeExploreRequest,
    current_user: User = Depends(get_current_user),
):
    result = await explore_code_tool(data.code, data.code_system)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return CodeExploreResponse(**result)


@router.get("/systems")
async def list_code_systems(current_user: User = Depends(get_current_user)):
    return await code_dict_service.get_all_systems()


@router.post("/validate")
async def validate_code(code: str, code_system: str = "ICD10_CN",
                        current_user: User = Depends(get_current_user)):
    return await code_dict_service.validate_code(code, code_system)


@router.post("/verify", response_model=CodeVerifyResponse)
async def verify_sequence(
    data: CodeVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    result = await verify_sequence_tool(
        data.encounter_id, data.diagnosis_codes, data.procedure_codes, data.evidence_pack_id
    )
    return CodeVerifyResponse(**result)
