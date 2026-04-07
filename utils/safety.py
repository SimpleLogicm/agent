import re
from typing import Optional, List

BLOCKED_KEYWORDS = [
    "DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE",
    "EXEC", "EXECUTE", "CALL", "COPY", "pg_",
]

BLOCKED_PATTERNS = [
    r";\s*(DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)",
    r"--",
    r"/\*",
    r"xp_",
    r"UNION\s+ALL\s+SELECT.*FROM\s+pg_",
]

WRITE_KEYWORDS = ["INSERT", "UPDATE", "DELETE"]


def validate_query(sql: str, read_only: bool = False, blocked_tables: Optional[List[str]] = None) -> dict:
    sql_upper = sql.upper().strip()

    for keyword in BLOCKED_KEYWORDS:
        pattern = rf'\b{keyword}\b'
        if re.search(pattern, sql_upper):
            return {"safe": False, "reason": f"Blocked keyword: {keyword}"}

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, sql_upper):
            return {"safe": False, "reason": f"Blocked pattern detected"}

    if read_only:
        for keyword in WRITE_KEYWORDS:
            if re.search(rf'\b{keyword}\b', sql_upper):
                return {"safe": False, "reason": f"Write operation not allowed in read-only mode: {keyword}"}

    if blocked_tables:
        for table in blocked_tables:
            if re.search(rf'\b{table.upper()}\b', sql_upper):
                return {"safe": False, "reason": f"Access to table '{table}' is blocked"}

    return {"safe": True}


def sanitize_table_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '', name)
