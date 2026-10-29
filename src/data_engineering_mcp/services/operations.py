import re
from typing import Any

from data_engineering_mcp.database.repository import Repository


class ServiceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|MERGE|EXEC|ATTACH|DETACH|REINDEX|VACUUM|PRAGMA)\b", re.IGNORECASE)


def validate_sql(sql: str) -> dict[str, Any]:
    normalized = sql.strip()
    warnings: list[str] = []
    if not normalized:
        return {"valid": False, "read_only": False, "warnings": ["SQL cannot be empty"]}
    if ";" in normalized.rstrip(";"):
        return {"valid": False, "read_only": False, "warnings": ["Multiple SQL statements are not allowed"]}
    if not re.match(r"^(SELECT|WITH)\b", normalized, re.IGNORECASE):
        return {"valid": False, "read_only": False, "warnings": ["Only SELECT and WITH queries are allowed"]}
    forbidden = FORBIDDEN_SQL.search(normalized)
    if forbidden:
        return {"valid": False, "read_only": False, "warnings": [f"Unsafe SQL keyword: {forbidden.group(1).upper()}"]}
    if "*" in normalized:
        warnings.append("Prefer explicit columns for stable contracts")
    return {"valid": True, "read_only": True, "warnings": warnings}


class OperationsService:
    def __init__(
        self,
        repository: Repository,
        max_rows: int = 100,
        max_log_rows: int | None = None,
        query_timeout_seconds: float = 2,
    ):
        self.repository = repository
        self.max_rows = max_rows
        self.max_log_rows = max_rows if max_log_rows is None else max_log_rows
        self.query_timeout_seconds = query_timeout_seconds

    def get_job_status(self, job_name: str) -> dict[str, Any]:
        result = self.repository.job_status(job_name)
        if not result:
            raise ServiceError("NOT_FOUND", f"Unknown job: {job_name}")
        return {"job_name": job_name, "status": result["status"], "last_run": result["started_at"], "duration_seconds": result["duration_seconds"], "records_processed": result["records_processed"]}

    def get_job_logs(self, job_name: str, run_id: str | None = None, severity: str | None = None, limit: int = 50) -> dict[str, Any]:
        if not self.repository.job_status(job_name):
            raise ServiceError("NOT_FOUND", f"Unknown job: {job_name}")
        logs = self.repository.logs(job_name, run_id, severity, min(limit, self.max_log_rows))
        if run_id and not logs:
            known = self.repository.connection.execute("SELECT 1 FROM etl_executions WHERE run_id = ? AND job_name = ?", (run_id, job_name)).fetchone()
            if not known:
                raise ServiceError("NOT_FOUND", f"Unknown run for job: {run_id}")
        return {"job_name": job_name, "run_id": run_id, "logs": logs}

    def get_job_history(self, job_name: str, days: int) -> dict[str, Any]:
        if not self.repository.job_status(job_name):
            raise ServiceError("NOT_FOUND", f"Unknown job: {job_name}")
        return {"job_name": job_name, "days": days, "executions": self.repository.history(job_name, days)}

    def get_database_schema(self, table_name: str) -> dict[str, Any]:
        result = self.repository.table_schema(table_name)
        if not result:
            raise ServiceError("NOT_FOUND", f"Unknown table: {table_name}")
        return result

    def execute_readonly_sql(self, sql: str, limit: int) -> dict[str, Any]:
        validation = validate_sql(sql)
        if not validation["valid"]:
            raise ServiceError("UNSAFE_SQL", validation["warnings"][0])
        try:
            return self.repository.execute_readonly(sql, min(limit, self.max_rows), self.query_timeout_seconds)
        except Exception as exc:
            raise ServiceError("QUERY_ERROR", "The read-only query could not be executed") from exc

    def search_documentation(self, query: str, top_k: int) -> dict[str, Any]:
        return {"query": query, "results": self.repository.search("documents", query, top_k)}

    def search_incidents(self, query: str, limit: int) -> dict[str, Any]:
        return {"query": query, "results": self.repository.search("incidents", query, limit)}

    def analyze_job_failure(self, job_name: str, run_id: str) -> dict[str, Any]:
        status = self.repository.connection.execute("SELECT * FROM etl_executions WHERE job_name = ? AND run_id = ?", (job_name, run_id)).fetchone()
        if not status:
            raise ServiceError("NOT_FOUND", f"Unknown run for job: {run_id}")
        logs = self.repository.logs(job_name, run_id, "ERROR", 20)
        previous_failures = self.repository.connection.execute("SELECT COUNT(*) FROM etl_executions WHERE job_name = ? AND status = 'FAILED' AND run_id != ?", (job_name, run_id)).fetchone()[0]
        errors = [log["message"] for log in logs]
        failure_type = "DATABASE_TIMEOUT" if any("timeout" in error.lower() and "database" in error.lower() for error in errors) else "UNKNOWN_FAILURE"
        recommendation = "Check database connectivity and connection pool limits" if failure_type == "DATABASE_TIMEOUT" else "Review the observed error and the relevant runbook"
        return {"job": job_name, "run_id": run_id, "observed_facts": {"status": status["status"], "errors": errors, "previous_failures": previous_failures}, "possible_cause": failure_type, "recommendation": recommendation}