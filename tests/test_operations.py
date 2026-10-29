import sqlite3

from data_engineering_mcp.database.database import connect, initialize_database
from data_engineering_mcp.services.operations import ServiceError, validate_sql


def test_job_status_and_history(operations):
    status = operations.get_job_status("Customer_Load")
    assert status["job_name"] == "Customer_Load"
    assert status["status"] in {"SUCCESS", "FAILED"}
    assert operations.get_job_history("Customer_Load", 365)["executions"]


def test_logs_are_bounded_and_structured(operations):
    result = operations.get_job_logs("Customer_Load", limit=100)
    assert len(result["logs"]) <= 10
    assert {"timestamp", "level", "message"} <= result["logs"][0].keys()


def test_unknown_job_is_structured_error(operations):
    try:
        operations.get_job_status("does_not_exist")
    except ServiceError as error:
        assert error.code == "NOT_FOUND"
    else:
        raise AssertionError("Expected ServiceError")


def test_sql_validation_rejects_writes_and_multiple_statements():
    assert validate_sql("SELECT * FROM customers")["valid"]
    assert not validate_sql("DROP TABLE customers")["valid"]
    assert not validate_sql("SELECT 1; DELETE FROM customers")["valid"]
    assert not validate_sql("SELECT 1; SELECT 2")["valid"]


def test_readonly_query_is_limited_and_returns_columns(operations):
    result = operations.execute_readonly_sql("SELECT customer_id, name FROM customers", 100)
    assert result["columns"] == ["customer_id", "name"]
    assert result["row_count"] == 10


def test_query_only_connection_rejects_writes(tmp_path):
    database_path = tmp_path / "readonly.db"
    initialize_database(database_path)
    connection = connect(database_path, query_only=True)
    try:
        assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 20
        try:
            connection.execute("DELETE FROM customers")
        except sqlite3.OperationalError as error:
            assert "readonly" in str(error).lower()
        else:
            raise AssertionError("Expected SQLite query-only mode to reject writes")
    finally:
        connection.close()


def test_query_execution_is_interrupted_after_timeout(operations):
    operations.query_timeout_seconds = 0.001
    sql = """
        WITH RECURSIVE numbers(value) AS (
            VALUES (0)
            UNION ALL
            SELECT value + 1 FROM numbers WHERE value < 100000000
        )
        SELECT sum(value) FROM numbers
    """
    try:
        operations.execute_readonly_sql(sql, 1)
    except ServiceError as error:
        assert error.code == "QUERY_ERROR"
    else:
        raise AssertionError("Expected the query timeout to interrupt execution")


def test_schema_documentation_incidents_and_failure_analysis(operations):
    assert operations.get_database_schema("orders")["table"] == "orders"
    assert operations.search_documentation("rollback", 5)["results"]
    assert operations.search_incidents("database timeout", 5)["results"]
    analysis = operations.analyze_job_failure("Customer_Load", "RUN-00081")
    assert analysis["possible_cause"] == "DATABASE_TIMEOUT"
    assert "observed_facts" in analysis