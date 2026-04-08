import uuid
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("agent")
from connectors.base import BaseConnector
from connectors.postgres import PostgresConnector
from connectors.sqlite import SQLiteConnector
from connectors.mysql import MySQLConnector
from connectors.mongodb import MongoDBConnector
from connectors.api_connector import APIConnector
from agent.schema_analyzer import SchemaAnalyzer
from agent.intent_classifier import IntentClassifier
from agent.query_generator import QueryGenerator
from agent.action_engine import ActionEngine
from agent.response_builder import ResponseBuilder
from agent.codebase_analyzer import CodebaseAnalyzer
from agent.business_logic import BusinessLogicLearner
from agent.memory import ConversationMemory
from agent.db_learner import DBBrain
from config import settings

DB_CONNECTORS = {
    "postgresql": PostgresConnector,
    "postgres": PostgresConnector,
    "sqlite": SQLiteConnector,
    "mysql": MySQLConnector,
    "mongodb": MongoDBConnector,
    "mongo": MongoDBConnector,
}


class AgentCore:
    def __init__(self):
        self.connector: Optional[BaseConnector] = None
        self.api_connector = APIConnector()
        self.schema_analyzer = SchemaAnalyzer()
        self.intent_classifier = IntentClassifier()
        self.query_generator = QueryGenerator()
        self.action_engine: Optional[ActionEngine] = None
        self.response_builder = ResponseBuilder()
        self.codebase_analyzer = CodebaseAnalyzer()
        self.business_logic = BusinessLogicLearner()
        self.memory = ConversationMemory()
        self.db_brain = DBBrain()

        self.is_ready = False
        self.db_type: str = ""
        self.analysis: Dict[str, Any] = {}
        self.codebase_info: Dict[str, Any] = {}
        self.business_info: Dict[str, Any] = {}

    def connect_database(self, db_type: str, **kwargs) -> Dict[str, Any]:
        db_type_lower = db_type.lower()
        connector_class = DB_CONNECTORS.get(db_type_lower)
        if not connector_class:
            return {
                "status": "error",
                "message": f"Unsupported database type: {db_type}. Supported: {list(DB_CONNECTORS.keys())}",
            }

        self.connector = connector_class()
        result = self.connector.connect(**kwargs)
        if result["status"] != "connected":
            self.connector = None
            return result

        self.db_type = db_type_lower
        self.action_engine = ActionEngine(self.connector)

        # FAST: Only get table names + columns (no row counts, no samples, no indexes)
        tables = self.connector.get_tables()
        raw_schema = {}
        for table in tables:
            if table in settings.BLOCKED_TABLES:
                continue
            try:
                raw_schema[table] = self.connector.get_table_schema(table)
            except Exception:
                raw_schema[table] = {"table": table, "columns": [], "foreign_keys": [], "indexes": []}

        self.analysis = self.schema_analyzer.analyze(raw_schema)

        # Build deep understanding of database (one-time, saved locally)
        from agent.llm import chat as llm_chat
        self.db_brain.learn(raw_schema, self.connector, llm_chat)

        self.business_info = {"workflows_learned": 0, "workflows": []}
        self.business_logic.domain = self.analysis.get("domain", "general")

        self.is_ready = True

        return {
            "status": "connected",
            "db_type": self.db_type,
            "database": result.get("database", ""),
            "domain": self.analysis.get("domain", "unknown"),
            "tables": self.analysis.get("tables", []),
            "workflows_learned": self.business_info.get("workflows_learned", 0),
            "available_actions": self.analysis.get("available_actions", [])[:10],
        }

    def connect_api(self, base_url: str, headers: Optional[Dict] = None,
                    openapi_url: Optional[str] = None) -> Dict[str, Any]:
        return self.api_connector.connect(
            base_url=base_url,
            headers=headers,
            openapi_url=openapi_url,
        )

    def analyze_codebase(self, project_path: str) -> Dict[str, Any]:
        self.codebase_info = self.codebase_analyzer.analyze(project_path)

        if self.is_ready and self.codebase_info.get("routes"):
            raw_schema = self.connector.get_full_schema()
            self.business_info = self.business_logic.learn(
                domain=self.analysis.get("domain", "general"),
                schema=raw_schema,
                codebase_info=self.codebase_info,
                project_path=project_path,
            )
            self.codebase_info["workflows_updated"] = self.business_info.get("workflows_learned", 0)

        return self.codebase_info

    def ask(self, question: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        if not session_id:
            session_id = "default"

        self.memory.add_message(session_id, "user", question)

        if not self.is_ready:
            return {"answer": "No database connected yet. Please connect a database first.", "suggestions": [], "data": None}

        import json as _json
        from agent.llm import chat as llm_chat

        domain = self.analysis.get("domain", "business")
        conversation_history = self.memory.get_context_window(session_id, last_n=8)
        raw_schema = self.schema_analyzer.schema

        # ─── Brain builds context ───
        t0 = time.time()
        db_context = self.db_brain.get_context(question, raw_schema)
        if not db_context:
            db_context = self.schema_analyzer.schema_summary[:2000]

        # Build clear people tables reference (sorted by records, most first)
        people_ref = ""
        if self.db_brain.people_search_tables:
            people_ref = "\n\nPEOPLE TABLES (sorted by record count, use first one that fits):\n"
            for pt in self.db_brain.people_search_tables[:8]:
                cols = pt.get("search_columns", [])
                display = pt.get("display_columns", [])
                sample = pt.get("sample_names", [""])[0] if pt.get("sample_names") else ""
                people_ref += f'  "{pt["table"]}" ({pt.get("row_count", 0)} records)\n'
                people_ref += f'    Search: {", ".join([chr(34)+c+chr(34) for c in cols])}\n'
                if display:
                    people_ref += f'    Display: {", ".join([chr(34)+c+chr(34) for c in display[:6]])}\n'
                if sample:
                    people_ref += f'    Sample: {sample}\n'

        # Build orders tables reference
        orders_ref = ""
        order_tables = self.db_brain.table_map.get("orders", [])
        if order_tables:
            orders_ref = "\n\nORDER TABLES:\n"
            for t in order_tables[:3]:
                if t in raw_schema:
                    cols = [c["name"] for c in raw_schema[t].get("columns", [])[:10]]
                    orders_ref += f'  "{t}" columns: {", ".join(cols)}\n'

        logger.info(f"  [1] Brain lookup: {round(time.time()-t0, 1)}s")

        # ─── ONE LLM call: generate SQL ───
        t0 = time.time()
        business = self.db_brain.summary or f"A {domain} business"

        sql_prompt = f"""You are a PostgreSQL expert. Business: {business}

{db_context}
{people_ref}
{orders_ref}

CONVERSATION HISTORY:
{conversation_history if conversation_history else "None"}

USER QUESTION: "{question}"

THINK STEP BY STEP:
1. Is this a greeting (hi/hello/thanks/bye)? → Return: NONE
2. Is user asking about a person? → Use PEOPLE TABLES above, search with ILIKE '%name%'
3. Is user asking "her/his/their"? → Look at conversation history, find who they mean, search again
4. Is user asking about orders/sales? → Use ORDER TABLES above, ORDER BY "created_at" DESC
5. Is user asking to count something? → Use COUNT(*)
6. Remove 's from names: "aanchal's" → search for "aanchal"

SQL RULES:
- ALL table and column names MUST be in double quotes
- Use ONLY exact table/column names from above
- ILIKE for name search (case insensitive)
- LIMIT 20
- If greeting/chat → NONE

Return ONLY the SQL. Nothing else."""

        sql = ""
        try:
            sql = llm_chat(sql_prompt, temperature=0.1)
            logger.info(f"  [2] SQL generated: {round(time.time()-t0, 1)}s → {sql[:80]}")
        except Exception as e:
            logger.error(f"  LLM error: {e}")

        # Clean SQL
        sql = sql.strip()
        if sql.startswith("```"):
            parts = sql.split("```")
            sql = parts[1] if len(parts) > 1 else ""
            if sql.startswith("sql"):
                sql = sql[3:]
            sql = sql.strip()
        if sql.upper() in ("NONE", "N/A", "") or not sql:
            sql = ""

        # ─── Execute SQL ───
        rows = []
        if sql:
            t0 = time.time()
            query_result = self.action_engine.execute({"sql": sql, "params": {}})
            if query_result.get("success"):
                rows = query_result.get("rows", [])
                logger.info(f"  [3] DB execute: {round(time.time()-t0, 1)}s → {len(rows)} rows")
            else:
                db_error = query_result.get("error", "")
                logger.warning(f"  [3] DB error, retrying: {db_error[:80]}")
                try:
                    fix_sql = llm_chat(f"""Fix this SQL error.
Error: {db_error[:300]}
Query: {sql}
{db_context[:1500]}
{people_info}
ALL names in double quotes. Return ONLY the fixed SQL.""", temperature=0.1).strip()
                    if fix_sql.startswith("```"):
                        fix_sql = fix_sql.split("```")[1].strip()
                        if fix_sql.startswith("sql"):
                            fix_sql = fix_sql[3:].strip()
                    query_result = self.action_engine.execute({"sql": fix_sql, "params": {}})
                    if query_result.get("success"):
                        rows = query_result.get("rows", [])
                        logger.info(f"  [3b] Retry: {len(rows)} rows")
                except Exception:
                    pass

        # ─── Build answer ───
        t0 = time.time()
        data_section = ""
        if rows:
            data_section = f"\n\nDatabase returned {len(rows)} rows:\n{_json.dumps(rows[:10], indent=2, default=str)}"
            if len(rows) > 10:
                data_section += f"\n(+ {len(rows)-10} more)"
        elif sql:
            data_section = "\n\nQuery returned no results."

        answer_prompt = f"""You are a polite AI assistant for a {domain} business. Always say "sir" or "ma'am".

User: "{question}"

Conversation history:
{conversation_history if conversation_history else "None"}
{data_section}

REPLY RULES:
- Start with "Sure sir!", "Here you go sir!", etc.
- If data found: show specific names, phone numbers, emails, amounts from the data
- If about a person: list their name, phone, email, address, company
- If "her/his number": use conversation history to find who, then show their phone
- If no data: say so politely and suggest what to try
- If general chat: respond naturally
- Use **bold** for key info
- Use bullet points for lists
- Keep it concise

Plain text only (no JSON):"""

        try:
            answer = llm_chat(answer_prompt, temperature=0.3)
            logger.info(f"  [4] Answer: {round(time.time()-t0, 1)}s")
        except Exception as e:
            logger.error(f"  Answer error: {e}")
            answer = f"Sure sir! I found {len(rows)} records." if rows else "I'm sorry sir, could you rephrase that?"

        suggestions = ["Show all customers", "Recent orders", "Top sales this month"]

        response = {
            "answer": answer,
            "suggestions": suggestions,
            "data": rows if rows else None,
        }

        self.memory.add_message(session_id, "agent", response.get("answer", ""),
                                metadata={"sql": sql})

        response["debug"] = {
            "sql": sql,
            "db_type": self.db_type,
            "session_id": session_id,
        }

        return response

    def get_schema(self) -> Dict[str, Any]:
        if not self.is_ready:
            return {"error": "No database connected"}
        return {
            "db_type": self.db_type,
            "domain": self.analysis.get("domain", "unknown"),
            "schema_summary": self.schema_analyzer.schema_summary,
            "tables": self.analysis.get("tables", []),
            "available_actions": self.analysis.get("available_actions", []),
            "workflows": self.business_info.get("workflows", []),
        }

    def disconnect(self):
        if self.connector:
            self.connector.disconnect()
        self.api_connector.disconnect()
        self.connector = None
        self.action_engine = None
        self.is_ready = False
        self.db_type = ""
        self.analysis = {}
        self.codebase_info = {}
        self.business_info = {}
