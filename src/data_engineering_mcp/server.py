import json
import logging
import time
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from data_engineering_mcp.config import settings
from data_engineering_mcp.database.database import connect, initialize_database
from data_engineering_mcp.database.repository import Repository
from data_engineering_mcp.schemas import (
    AnalyzeFailureRequest,
    ExecuteSqlRequest,
    JobHistoryRequest,
    JobLogsRequest,
    JobStatusRequest,
    SchemaRequest,
    SearchDocumentationRequest,
    SearchIncidentsRequest,
    ValidateSqlRequest,
)
from data_engineering_mcp.services.operations import OperationsService, ServiceError, validate_sql as validate_sql_query


logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
mcp = FastMCP("Data Engineering MCP Server")
_service: OperationsService | None = None


def service() -> OperationsService:
    global _service
    if _service is None:
        initialize_database(settings.sqlite_path)
        _service = OperationsService(Repository(connect(settings.sqlite_path)), settings.max_query_rows)
    return _service


def _call(tool_name: str, action: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    try:
        result = action()
        logger.info("audit request_id=%s tool=%s status=success duration_ms=%.2f metadata=%s", request_id, tool_name, (time.perf_counter() - started) * 1000, metadata)
        return result
    except ServiceError as exc:
        logger.warning("audit request_id=%s tool=%s status=error error_type=%s duration_ms=%.2f", request_id, tool_name, exc.code, (time.perf_counter() - started) * 1000)
        return {"error": exc.code, "message": exc.message, "request_id": request_id}
    except ValidationError as exc:
        logger.warning("audit request_id=%s tool=%s status=invalid_input", request_id, tool_name)
        return {"error": "INVALID_INPUT", "message": "Tool arguments failed validation", "details": exc.errors(include_url=False), "request_id": request_id}
    except Exception:
        logger.exception("tool failure request_id=%s tool=%s", request_id, tool_name)
        return {"error": "INTERNAL_ERROR", "message": "The tool failed unexpectedly", "request_id": request_id}


@mcp.tool()
def get_job_status(job_name: str) -> dict[str, Any]:
    """Return the latest execution status for an ETL job."""
    return _call("get_job_status", lambda: service().get_job_status(JobStatusRequest(job_name=job_name).job_name), {"job_name": job_name})


@mcp.tool()
def get_job_logs(job_name: str, run_id: str | None = None, severity: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Return bounded structured logs for an ETL job execution."""
    return _call("get_job_logs", lambda: (lambda request: service().get_job_logs(request.job_name, request.run_id, request.severity, request.limit))(JobLogsRequest(job_name=job_name, run_id=run_id, severity=severity, limit=limit)), {"job_name": job_name, "run_id": run_id, "limit": limit})


@mcp.tool()
def get_job_history(job_name: str, days: int = 30) -> dict[str, Any]:
    """Return recent executions for an ETL job."""
    return _call("get_job_history", lambda: (lambda request: service().get_job_history(request.job_name, request.days))(JobHistoryRequest(job_name=job_name, days=days)), {"job_name": job_name, "days": days})


@mcp.tool()
def get_database_schema(table_name: str) -> dict[str, Any]:
    """Return table columns and indexes without credentials."""
    return _call("get_database_schema", lambda: service().get_database_schema(SchemaRequest(table_name=table_name).table_name), {"table_name": table_name})


@mcp.tool()
def validate_sql(sql: str) -> dict[str, Any]:
    """Check whether SQL is a single safe read-only query."""
    try:
        return validate_sql_query(ValidateSqlRequest(sql=sql).sql)
    except ValidationError as exc:
        return {"error": "INVALID_INPUT", "message": "Tool arguments failed validation", "details": exc.errors(include_url=False)}


@mcp.tool()
def execute_readonly_sql(sql: str, limit: int = 50) -> dict[str, Any]:
    """Execute a bounded SELECT or WITH query against the synthetic database."""
    return _call("execute_readonly_sql", lambda: (lambda request: service().execute_readonly_sql(request.sql, request.limit))(ExecuteSqlRequest(sql=sql, limit=limit)), {"sql_length": len(sql), "limit": limit})


@mcp.tool()
def search_documentation(query: str, top_k: int = 5) -> dict[str, Any]:
    """Search synthetic data engineering runbooks."""
    return _call("search_documentation", lambda: (lambda request: service().search_documentation(request.query, request.top_k))(SearchDocumentationRequest(query=query, top_k=top_k)), {"query_length": len(query), "top_k": top_k})


@mcp.tool()
def search_incidents(query: str, limit: int = 5) -> dict[str, Any]:
    """Search historical synthetic incidents."""
    return _call("search_incidents", lambda: (lambda request: service().search_incidents(request.query, request.limit))(SearchIncidentsRequest(query=query, limit=limit)), {"query_length": len(query), "limit": limit})


@mcp.tool()
def analyze_job_failure(job_name: str, run_id: str) -> dict[str, Any]:
    """Prepare deterministic evidence for a failed ETL run."""
    return _call("analyze_job_failure", lambda: (lambda request: service().analyze_job_failure(request.job_name, request.run_id))(AnalyzeFailureRequest(job_name=job_name, run_id=run_id)), {"job_name": job_name, "run_id": run_id})


@mcp.resource("resource://jobs")
def jobs_resource() -> str:
    """Read-only catalog of available ETL jobs."""
    rows = service().repository.connection.execute("SELECT job_name, owner, schedule, description FROM etl_jobs ORDER BY job_name")
    return json.dumps([dict(row) for row in rows], indent=2)


@mcp.resource("resource://incidents")
def incidents_resource() -> str:
    """Read-only historical incident catalog."""
    rows = service().repository.connection.execute("SELECT incident_id, title, category, occurred_at FROM incidents ORDER BY occurred_at DESC")
    return json.dumps([dict(row) for row in rows], indent=2)


@mcp.resource("resource://database/schema")
def database_schema_resource() -> str:
    """Read-only list of synthetic database tables."""
    rows = service().repository.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return json.dumps([row[0] for row in rows], indent=2)


@mcp.resource("resource://documentation")
def documentation_resource() -> str:
    """Read-only documentation catalog."""
    rows = service().repository.connection.execute("SELECT document_id, title, section, source FROM documents ORDER BY title")
    return json.dumps([dict(row) for row in rows], indent=2)


@mcp.prompt()
def investigate_etl_failure(job_name: str, run_id: str) -> str:
    return f"""Investigate ETL failure for job {job_name}, run {run_id}.\n1. Call get_job_status.\n2. Call get_job_logs for the run.\n3. Inspect recent history.\n4. Search similar incidents.\n5. Search documentation.\n6. Produce an evidence-based RCA separating observed facts, possible cause, and recommendation."""


@mcp.prompt()
def analyze_sql(sql: str) -> str:
    return f"""Analyze this SQL safely: {sql}\n1. Call validate_sql_tool.\n2. Inspect database schema if required.\n3. Identify correctness and performance risks.\n4. Explain optimization opportunities without executing unsafe statements."""


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()