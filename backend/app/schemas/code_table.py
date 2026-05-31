# Code Table schemas
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CodeTableResponse(BaseModel):
    id: str
    name: str
    code_system: str = ""
    description: str = ""
    version: str = ""
    is_active: bool = True
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CodeTableListResponse(BaseModel):
    tables: list[CodeTableResponse]


class CodeMappingResponse(BaseModel):
    id: str
    source_code: str
    source_table: str
    target_code: str
    target_table: str
    relationship: str = "exact"
    confidence: float = 1.0


class CodeTableCreateRequest(BaseModel):
    name: str
    code_system: str
    description: str = ""
    version: str = ""
    is_active: bool = True
    is_default: bool = False


class CodeTableDeleteResponse(BaseModel):
    id: str
    name: str
