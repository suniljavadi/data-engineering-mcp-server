from typing import Any, Literal

from pydantic import BaseModel, Field


class JobStatusRequest(BaseModel):
    job_name: str = Field(min_length=1, max_length=100)


class JobLogsRequest(JobStatusRequest):
    run_id: str | None = Field(default=None, max_length=100)
    severity: Literal["DEBUG", "INFO", "WARN", "ERROR"] | None = None
    limit: int = Field(default=50, ge=1, le=100)


class JobHistoryRequest(JobStatusRequest):
    days: int = Field(default=30, ge=1, le=365)


class SchemaRequest(BaseModel):
    table_name: str = Field(min_length=1, max_length=100)


class ValidateSqlRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)


class ExecuteSqlRequest(ValidateSqlRequest):
    limit: int = Field(default=50, ge=1, le=100)


class SearchDocumentationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchIncidentsRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class AnalyzeFailureRequest(BaseModel):
    job_name: str = Field(min_length=1, max_length=100)
    run_id: str = Field(min_length=1, max_length=100)


class SqlValidationResult(BaseModel):
    valid: bool
    read_only: bool
    warnings: list[str]


class ToolError(BaseModel):
    error: str
    message: str
    details: dict[str, Any] = {}