from typing import Optional, List, Dict, Any
from connectors.base import BaseConnector


class MySQLConnector(BaseConnector):
    db_type = "mysql"

    def __init__(self):
        self.conn = None
        self.database: str = ""

    def connect(self, **kwargs) -> Dict[str, Any]:
        try:
            import mysql.connector
        except ImportError:
            return {"status": "error", "message": "mysql-connector-python not installed. Run: pip install mysql-connector-python"}

        self.database = kwargs.get("database", "")
        try:
            self.conn = mysql.connector.connect(
                host=kwargs.get("host", "localhost"),
                port=kwargs.get("port", 3306),
                database=self.database,
                user=kwargs.get("user", "root"),
                password=kwargs.get("password", ""),
            )
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return {"status": "connected", "database": self.database}
        except Exception as e:
            self.conn = None
            return {"status": "error", "message": str(e)}

    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    @property
    def is_connected(self) -> bool:
        return self.conn is not None and self.conn.is_connected()

    def get_tables(self) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return tables

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        cursor = self.conn.cursor(dictionary=True)

        cursor.execute(f"DESCRIBE `{table_name}`")
        raw_columns = cursor.fetchall()

        columns = []
        for col in raw_columns:
            columns.append({
                "name": col["Field"],
                "type": col["Type"],
                "nullable": col["Null"] == "YES",
                "default": col["Default"],
                "primary_key": col["Key"] == "PRI",
            })

        cursor.execute(f"""
            SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            AND REFERENCED_TABLE_NAME IS NOT NULL
        """, (self.database, table_name))
        fk_rows = cursor.fetchall()

        foreign_keys = []
        for fk in fk_rows:
            foreign_keys.append({
                "columns": [fk["COLUMN_NAME"]],
                "referred_table": fk["REFERENCED_TABLE_NAME"],
                "referred_columns": [fk["REFERENCED_COLUMN_NAME"]],
            })

        cursor.execute(f"SHOW INDEX FROM `{table_name}`")
        idx_rows = cursor.fetchall()
        idx_map = {}
        for idx in idx_rows:
            name = idx["Key_name"]
            if name not in idx_map:
                idx_map[name] = {"name": name, "columns": [], "unique": not idx["Non_unique"]}
            idx_map[name]["columns"].append(idx["Column_name"])
        indexes = list(idx_map.values())

        cursor.close()
        return {
            "table": table_name,
            "columns": columns,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }

    def get_row_count(self, table_name: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        count = cursor.fetchone()[0]
        cursor.close()
        return count

    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict]:
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM `{table_name}` LIMIT %s", (limit,))
        rows = [{k: self._serialize(v) for k, v in row.items()} for row in cursor.fetchall()]
        cursor.close()
        return rows

    def execute_query(self, query: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            cursor = self.conn.cursor(dictionary=True)
            if params:
                formatted = query
                for key, val in params.items():
                    formatted = formatted.replace(f":{key}", "%s")
                cursor.execute(formatted, list(params.values()))
            else:
                cursor.execute(query)

            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = [{k: self._serialize(v) for k, v in row.items()} for row in cursor.fetchall()]
                cursor.close()
                return {"success": True, "columns": columns, "rows": rows, "row_count": len(rows)}
            else:
                self.conn.commit()
                affected = cursor.rowcount
                cursor.close()
                return {"success": True, "affected_rows": affected}
        except Exception as e:
            return {"success": False, "error": str(e)}
