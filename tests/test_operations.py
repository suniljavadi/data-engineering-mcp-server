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


def test_schema_documentation_incidents_and_failure_analysis(operations):
    assert operations.get_database_schema("orders")["table"] == "orders"
    assert operations.search_documentation("rollback", 5)["results"]
    assert operations.search_incidents("database timeout", 5)["results"]
    analysis = operations.analyze_job_failure("Customer_Load", "RUN-00081")
    assert analysis["possible_cause"] == "DATABASE_TIMEOUT"
    assert "observed_facts" in analysis