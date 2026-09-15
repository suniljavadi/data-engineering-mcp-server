from pathlib import Path

import pytest

from data_engineering_mcp.database.database import connect, initialize_database
from data_engineering_mcp.database.repository import Repository
from data_engineering_mcp.services.operations import OperationsService


@pytest.fixture
def operations(tmp_path: Path) -> OperationsService:
    database_path = tmp_path / "test.db"
    initialize_database(database_path)
    return OperationsService(Repository(connect(database_path)), max_rows=10)