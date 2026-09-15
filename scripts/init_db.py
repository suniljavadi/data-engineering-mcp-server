from data_engineering_mcp.config import settings
from data_engineering_mcp.database.database import initialize_database


if __name__ == "__main__":
    initialize_database(settings.sqlite_path)
    print(f"Initialized {settings.sqlite_path}")