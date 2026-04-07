from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from connectors.base import BaseConnector


class PostgresConnector(BaseConnector):
    db_type = "postgresql"

    def __init__(self):
        self.engine: Optional[Engine] = None
        self.db_url: str = ""

    def connect(self, **kwargs) -> Dict[str, Any]:
        host = kwargs.get("host", "localhost")
        port = kwargs.get("port", 5432)
        database = kwargs.get("database", "")
        user = kwargs.get("user", "postgres")
        password = kwargs.get("password", "")

        self.db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        try:
            self.engine = create_engine(self.db_url, pool_pre_ping=True)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"status": "connected", "database": database}
        except Exception as e:
            self.engine = None
            return {"status": "error", "message": str(e)}

    def disconnect(self):
        if self.engine:
            self.engine.dispose()
            self.engine = None

    @property
    def is_connected(self) -> bool:
        return self.engine is not None

    def get_tables(self) -> List[str]:
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        inspector = inspect(self.engine)

        columns = []
        for col in inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "default": str(col.get("default")) if col.get("default") else None,
                "primary_key": False,
            })

        pk = inspector.get_pk_constraint(table_name)
        pk_columns = pk.get("constrained_columns", []) if pk else []
        for col in columns:
            if col["name"] in pk_columns:
                col["primary_key"] = True

        foreign_keys = []
        for fk in inspector.get_foreign_keys(table_name):
            foreign_keys.append({
                "columns": fk["constrained_columns"],
                "referred_table": fk["referred_table"],
                "referred_columns": fk["referred_columns"],
            })

        indexes = []
        for idx in inspector.get_indexes(table_name):
            indexes.append({
                "name": idx["name"],
                "columns": idx["column_names"],
                "unique": idx.get("unique", False),
            })

        return {
            "table": table_name,
            "columns": columns,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }

    def get_row_count(self, table_name: str) -> int:
        with self.engine.connect() as conn:
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
            return result.scalar()

    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict]:
        with self.engine.connect() as conn:
            result = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT :limit'), {"limit": limit})
            columns = result.keys()
            rows = []
            for row in result:
                rows.append({col: self._serialize(val) for col, val in zip(columns, row)})
            return rows

    def execute_query(self, query: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                if result.returns_rows:
                    columns = list(result.keys())
                    rows = [
                        {col: self._serialize(val) for col, val in zip(columns, row)}
                        for row in result
                    ]
                    return {"success": True, "columns": columns, "rows": rows, "row_count": len(rows)}
                else:
                    conn.commit()
                    return {"success": True, "affected_rows": result.rowcount}
        except Exception as e:
            return {"success": False, "error": str(e)}
