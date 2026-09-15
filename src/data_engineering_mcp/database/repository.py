import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


class Repository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def job_status(self, job_name: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT e.*, j.owner, j.schedule FROM etl_executions e JOIN etl_jobs j USING(job_name) WHERE job_name = ? ORDER BY started_at DESC LIMIT 1", (job_name,)).fetchone()
        return dict(row) if row else None

    def logs(self, job_name: str, run_id: str | None, severity: str | None, limit: int) -> list[dict[str, Any]]:
        query = "SELECT l.timestamp, l.level, l.message, l.run_id FROM etl_logs l JOIN etl_executions e USING(run_id) WHERE e.job_name = ?"
        params: list[Any] = [job_name]
        if run_id:
            query += " AND l.run_id = ?"; params.append(run_id)
        if severity:
            query += " AND l.level = ?"; params.append(severity)
        query += " ORDER BY l.timestamp DESC LIMIT ?"; params.append(limit)
        return [dict(row) for row in self.connection.execute(query, params)]

    def history(self, job_name: str, days: int) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        return [dict(row) for row in self.connection.execute("SELECT run_id, status, started_at, duration_seconds, records_processed FROM etl_executions WHERE job_name = ? AND started_at >= ? ORDER BY started_at DESC", (job_name, cutoff))]

    def table_schema(self, table_name: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            return None
        table = self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)).fetchone()
        if not table:
            return None
        columns = [dict(row) for row in self.connection.execute(f'PRAGMA table_info("{table_name}")')]
        indexes = [dict(row) for row in self.connection.execute(f'PRAGMA index_list("{table_name}")')]
        return {"table": table_name, "columns": columns, "indexes": indexes}

    def search(self, table: str, query: str, limit: int) -> list[dict[str, Any]]:
        terms = [f"%{term}%" for term in query.split()]
        if table == "documents":
            clauses = ["(title LIKE ? OR section LIKE ? OR content LIKE ?)" for _ in terms]
            sql = f"SELECT document_id, title, section, content, source FROM documents WHERE {' AND '.join(clauses)} ORDER BY title LIMIT ?"
            params = tuple(value for term in terms for value in (term, term, term)) + (limit,)
        else:
            clauses = ["(title LIKE ? OR category LIKE ? OR description LIKE ? OR resolution LIKE ?)" for _ in terms]
            sql = f"SELECT incident_id, title, category, description, resolution, occurred_at FROM incidents WHERE {' AND '.join(clauses)} ORDER BY occurred_at DESC LIMIT ?"
            params = tuple(value for term in terms for value in (term, term, term, term)) + (limit,)
        return [dict(row) for row in self.connection.execute(sql, params)]

    def execute_readonly(self, sql: str, limit: int) -> dict[str, Any]:
        cursor = self.connection.execute(sql)
        rows = [dict(row) for row in cursor.fetchmany(limit)]
        return {"columns": [description[0] for description in cursor.description or []], "rows": rows, "row_count": len(rows)}
