from connectors.postgres import PostgresConnector
from utils.safety import validate_query
from config import settings


class ActionEngine:
    def __init__(self, connector: PostgresConnector):
        self.connector = connector

    def execute(self, query_info: dict) -> dict:
        sql = query_info.get("sql", "")
        params = query_info.get("params", {})

        if not sql:
            return {"success": False, "error": "No SQL query generated"}

        validation = validate_query(
            sql,
            read_only=settings.READ_ONLY_MODE,
            blocked_tables=settings.BLOCKED_TABLES,
        )
        if not validation["safe"]:
            return {"success": False, "error": f"Query blocked: {validation['reason']}"}

        result = self.connector.execute_query(sql, params)
        return result
