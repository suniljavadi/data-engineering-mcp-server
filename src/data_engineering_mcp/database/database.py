import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, revenue REAL NOT NULL);
CREATE TABLE IF NOT EXISTS products (product_id INTEGER PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, order_date TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_items (order_id INTEGER NOT NULL, product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, PRIMARY KEY (order_id, product_id));
CREATE TABLE IF NOT EXISTS etl_jobs (job_name TEXT PRIMARY KEY, owner TEXT NOT NULL, schedule TEXT NOT NULL, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS etl_executions (run_id TEXT PRIMARY KEY, job_name TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, duration_seconds INTEGER, records_processed INTEGER);
CREATE TABLE IF NOT EXISTS etl_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, timestamp TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS incidents (incident_id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL, resolution TEXT NOT NULL, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (document_id TEXT PRIMARY KEY, title TEXT NOT NULL, section TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_execution_job ON etl_executions(job_name, started_at);
CREATE INDEX IF NOT EXISTS idx_logs_run ON etl_logs(run_id, timestamp);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        seed(connection)


def seed(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM etl_jobs").fetchone()[0]:
        return
    connection.executemany("INSERT INTO customers VALUES (?, ?, ?)", [(i, f"Customer {i}", i * 1250.5) for i in range(1, 21)])
    connection.executemany("INSERT INTO products VALUES (?, ?, ?)", [(i, f"Product {i}", i * 9.99) for i in range(1, 11)])
    connection.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", [(i, (i % 20) + 1, f"2026-09-{(i % 15) + 1:02d}", "COMPLETE") for i in range(1, 51)])
    connection.executemany("INSERT INTO order_items VALUES (?, ?, ?)", [(i, (i % 10) + 1, (i % 4) + 1) for i in range(1, 51)])
    jobs = [(f"{name}_Load", "data-platform", "0 * * * *", f"Loads {name.lower()} data") for name in ["Customer", "Order", "Product", "Inventory", "Invoice", "Payment", "Shipment", "Marketing", "Support", "Analytics"]]
    connection.executemany("INSERT INTO etl_jobs VALUES (?, ?, ?, ?)", jobs)
    executions = []
    logs = []
    failure_messages = ["Database connection timeout", "Deadlock detected", "Missing input file", "API timeout", "Authentication failure", "Schema mismatch", "Data quality failure", "Connection failure"]
    for index in range(1, 121):
        job = jobs[(index - 1) % len(jobs)][0]
        failed = index % 9 == 0
        run_id = f"RUN-{index:05d}"
        executions.append((run_id, job, "FAILED" if failed else "SUCCESS", f"2026-09-{(index % 15) + 1:02d}T{index % 24:02d}:15:00", 342 if failed else 120, 125430 if not failed else 0))
        message = "Database connection timeout" if failed and job == "Customer_Load" else failure_messages[index % len(failure_messages)]
        logs.append((run_id, f"2026-09-{(index % 15) + 1:02d}T{index % 24:02d}:20:00", "ERROR" if failed else "INFO", message if failed else "Execution completed"))
        logs.append((run_id, f"2026-09-{(index % 15) + 1:02d}T{index % 24:02d}:19:00", "INFO", "Extract phase started"))
        logs.append((run_id, f"2026-09-{(index % 15) + 1:02d}T{index % 24:02d}:21:00", "WARN" if failed else "INFO", "Retry scheduled" if failed else "Load phase completed"))
    connection.executemany("INSERT INTO etl_executions VALUES (?, ?, ?, ?, ?, ?)", executions)
    connection.executemany("INSERT INTO etl_logs (run_id, timestamp, level, message) VALUES (?, ?, ?, ?)", logs)
    incidents = [(f"INC-{i:03d}", failure_messages[i % len(failure_messages)], "ETL", f"Historical incident involving {failure_messages[i % len(failure_messages)].lower()}.", "Review service health and retry policy.", f"2026-08-{(i % 28) + 1:02d}") for i in range(1, 36)]
    connection.executemany("INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?)", incidents)
    docs = [(f"DOC-{i:03d}", title, section, content, "synthetic://data-platform/runbook") for i, (title, section, content) in enumerate([
        ("Customer Load Rollback", "Rollback", "Stop downstream jobs, restore the last valid partition, and replay Customer_Load after database connectivity is confirmed."),
        ("Database Timeout Runbook", "Connectivity", "Check database health, connection pool limits, and network latency before increasing client timeouts."),
        ("Deadlock Troubleshooting", "Reliability", "Inspect competing transactions and retry with bounded exponential backoff."),
        ("Schema Change Process", "Governance", "Publish a compatible schema first, backfill consumers, then remove deprecated fields."),
        ("Data Quality Checks", "Quality", "Validate null rates, uniqueness, referential integrity, and freshness before publishing."),
        ("API Timeout Runbook", "Connectivity", "Check upstream rate limits and request identifiers, then replay only idempotent requests."),
        ("Authentication Failure", "Security", "Verify service identity rotation and scope configuration without logging credentials."),
        ("Missing File Recovery", "Ingestion", "Confirm the expected arrival window and replay the upstream delivery."),
        ("ETL Observability", "Operations", "Track run status, duration, records processed, and structured error logs."),
        ("Read Only SQL Policy", "Security", "Only SELECT and WITH queries are accepted by the analytics query tool."),
    ], start=1)]
    connection.executemany("INSERT INTO documents VALUES (?, ?, ?, ?, ?)", docs)