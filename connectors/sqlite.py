import sqlite3
import os
from typing import Optional, List, Dict, Any
from connectors.base import BaseConnector


class SQLiteConnector(BaseConnector):
    db_type = "sqlite"

    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        self.db_path: str = ""

    def connect(self, **kwargs) -> Dict[str, Any]:
        self.db_path = kwargs.get("database", kwargs.get("path", ""))
        if not self.db_path:
            return {"status": "error", "message": "Database path is required"}

        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("SELECT 1")
            return {"status": "connected", "database": os.path.basename(self.db_path)}
        except Exception as e:
            self.conn = None
            return {"status": "error", "message": str(e)}

    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    @property
    def is_connected(self) -> bool:
        return self.conn is not None

    def get_tables(self) -> List[str]:
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        cursor = self.conn.execute(f"PRAGMA table_info('{table_name}')")
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "name": row[1],
                "type": row[2] or "TEXT",
                "nullable": not row[3],
                "default": row[4],
                "primary_key": bool(row[5]),
            })

        cursor = self.conn.execute(f"PRAGMA foreign_key_list('{table_name}')")
        foreign_keys = []
        for row in cursor.fetchall():
            foreign_keys.append({
                "columns": [row[3]],
                "referred_table": row[2],
                "referred_columns": [row[4]],
            })

        cursor = self.conn.execute(f"PRAGMA index_list('{table_name}')")
        indexes = []
        for row in cursor.fetchall():
            idx_cursor = self.conn.execute(f"PRAGMA index_info('{row[1]}')")
            idx_columns = [r[2] for r in idx_cursor.fetchall()]
            indexes.append({
                "name": row[1],
                "columns": idx_columns,
                "unique": bool(row[2]),
            })

        return {
            "table": table_name,
            "columns": columns,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }

    def get_row_count(self, table_name: str) -> int:
        cursor = self.conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        return cursor.fetchone()[0]

    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict]:
        cursor = self.conn.execute(f"SELECT * FROM [{table_name}] LIMIT ?", (limit,))
        columns = [desc[0] for desc in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append({col: self._serialize(val) for col, val in zip(columns, row)})
        return rows

    def execute_query(self, query: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            if params:
                converted = {}
                for k, v in params.items():
                    converted[k] = v
                cursor = self.conn.execute(query, converted)
            else:
                cursor = self.conn.execute(query)

            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = [
                    {col: self._serialize(val) for col, val in zip(columns, row)}
                    for row in cursor.fetchall()
                ]
                return {"success": True, "columns": columns, "rows": rows, "row_count": len(rows)}
            else:
                self.conn.commit()
                return {"success": True, "affected_rows": cursor.rowcount}
        except Exception as e:
            return {"success": False, "error": str(e)}
