import sqlite3
import json
import os
import time
from typing import List, Dict, Any, Optional

MEMORY_DB = "agent_memory.db"


class ConversationMemory:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or MEMORY_DB
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        return sqlite3.connect(self.db_path)

    def _close_conn(self, conn: sqlite3.Connection):
        if conn is not self._conn:
            conn.close()

    def _init_db(self):
        if self.db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:")
            conn = self._conn
        else:
            conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                timestamp REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_type TEXT NOT NULL,
                fact_key TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'user',
                timestamp REAL NOT NULL,
                UNIQUE(fact_type, fact_key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_type ON learned_facts(fact_type)
        """)
        conn.commit()
        self._close_conn(conn)

    def add_message(self, session_id: str, role: str, content: str,
                    metadata: Optional[Dict] = None):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO conversations (session_id, role, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, json.dumps(metadata or {}), time.time()),
        )
        conn.commit()
        self._close_conn(conn)

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT role, content, metadata, timestamp FROM conversations WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        )
        messages = []
        for row in cursor.fetchall():
            messages.append({
                "role": row[0],
                "content": row[1],
                "metadata": json.loads(row[2]),
                "timestamp": row[3],
            })
        self._close_conn(conn)
        return list(reversed(messages))

    def get_context_window(self, session_id: str, last_n: int = 5) -> str:
        history = self.get_history(session_id, limit=last_n)
        if not history:
            return ""

        lines = ["Previous conversation:"]
        for msg in history:
            role = "User" if msg["role"] == "user" else "Agent"
            content = msg["content"][:200]
            lines.append(f"  {role}: {content}")
        return "\n".join(lines)

    def learn_fact(self, fact_type: str, fact_key: str, fact_value: str,
                   confidence: float = 1.0, source: str = "auto"):
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO learned_facts (fact_type, fact_key, fact_value, confidence, source, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(fact_type, fact_key) DO UPDATE SET
               fact_value = excluded.fact_value,
               confidence = excluded.confidence,
               timestamp = excluded.timestamp""",
            (fact_type, fact_key, fact_value, confidence, source, time.time()),
        )
        conn.commit()
        self._close_conn(conn)

    def get_facts(self, fact_type: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if fact_type:
            cursor = conn.execute(
                "SELECT fact_type, fact_key, fact_value, confidence, source FROM learned_facts WHERE fact_type = ? ORDER BY confidence DESC",
                (fact_type,),
            )
        else:
            cursor = conn.execute(
                "SELECT fact_type, fact_key, fact_value, confidence, source FROM learned_facts ORDER BY fact_type, confidence DESC"
            )
        facts = []
        for row in cursor.fetchall():
            facts.append({
                "type": row[0],
                "key": row[1],
                "value": row[2],
                "confidence": row[3],
                "source": row[4],
            })
        self._close_conn(conn)
        return facts

    def get_facts_context(self) -> str:
        facts = self.get_facts()
        if not facts:
            return ""

        lines = ["Known facts:"]
        for f in facts[:20]:
            lines.append(f"  [{f['type']}] {f['key']}: {f['value']}")
        return "\n".join(lines)

    def clear_session(self, session_id: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
        self._close_conn(conn)

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT session_id, COUNT(*) as msg_count, MIN(timestamp) as started, MAX(timestamp) as last_active
               FROM conversations GROUP BY session_id ORDER BY last_active DESC"""
        )
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                "session_id": row[0],
                "message_count": row[1],
                "started": row[2],
                "last_active": row[3],
            })
        self._close_conn(conn)
        return sessions
