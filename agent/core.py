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

        # Skip business logic learning for large DBs (do it lazily)
        if len(tables) < 50:
            self.business_info = self.business_logic.learn(
                domain=self.analysis.get("domain", "general"),
                schema=raw_schema,
            )
        else:
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

        tables_list = self.analysis.get("tables", [])
        domain = self.analysis.get("domain", "business")
        conversation_history = self.memory.get_context_window(session_id, last_n=8)
        q_lower = question.lower().strip()

        # ─── Quick greetings (no LLM) ───
        greetings = {"hi", "hello", "hey", "hii", "hiii", "yo", "sup", "good morning", "good evening", "good afternoon", "thanks", "thank you", "bye", "ok", "okay"}
        if q_lower.rstrip("!.,") in greetings:
            msg = "Hello sir/ma'am! Welcome! I'm your AI assistant connected to your database. How can I help you today?"
            if q_lower in ("thanks", "thank you"):
                msg = "You're welcome sir/ma'am! Let me know if you need anything else."
            if q_lower in ("bye",):
                msg = "Goodbye sir/ma'am! Have a great day!"
            self.memory.add_message(session_id, "agent", msg)
            return {"answer": msg, "suggestions": ["Show all customers", "Recent orders", "Top sales this month"], "data": None}

        # ─── Find relevant tables ───
        t0 = time.time()
        relevant_schema = self.schema_analyzer.find_relevant_tables(question, max_tables=10)
        if not relevant_schema:
            relevant_schema = self.schema_analyzer.schema_summary[:2000]
        logger.info(f"  [1] Find tables: {round(time.time()-t0, 1)}s")

        # ─── Step 1: Generate SQL (always try to query) ───
        t0 = time.time()
        sql_prompt = f"""Generate a PostgreSQL query for this question. ALWAYS generate SQL even if unsure.

DATABASE TABLES (use ONLY these exact names in double quotes):
{relevant_schema[:2500]}

CONVERSATION HISTORY:
{conversation_history if conversation_history else "None"}

USER QUESTION: "{question}"

RULES:
- ALWAYS generate a SELECT query. Do NOT say you can't find data.
- Use ONLY table and column names from the schema above
- ALL names in double quotes: SELECT "col" FROM "table"
- For names/people: use ILIKE '%name%' for fuzzy search
- For "tell me more" or "full detail": look at conversation history and expand the previous query with SELECT *
- Add LIMIT 20
- If truly no SQL possible (pure greeting), respond with just: NONE

Return ONLY the SQL query. Nothing else."""

        try:
            sql = llm_chat(sql_prompt, temperature=0.1)
            logger.info(f"  [2] SQL generated: {round(time.time()-t0, 1)}s → {sql[:80]}")
        except Exception as e:
            logger.error(f"  LLM error: {e}")
            sql = ""

        # Clean SQL
        sql = sql.strip()
        if sql.startswith("```"):
            lines = sql.split("```")
            sql = lines[1] if len(lines) > 1 else ""
            if sql.startswith("sql"):
                sql = sql[3:]
            sql = sql.strip()
        if sql.upper() in ("NONE", "N/A", ""):
            sql = ""

        # ─── Step 2: Execute SQL ───
        rows = []
        if sql:
            t0 = time.time()
            query_result = self.action_engine.execute({"sql": sql, "params": {}})
            if query_result.get("success"):
                rows = query_result.get("rows", [])
                logger.info(f"  [3] DB execute: {round(time.time()-t0, 1)}s → {len(rows)} rows")
            else:
                db_error = query_result.get("error", "")
                logger.warning(f"  [3] DB error, retrying: {db_error[:100]}")
                try:
                    fix_sql = llm_chat(f"""Fix this SQL. Error: {db_error[:300]}
Query: {sql}
Schema: {relevant_schema[:1500]}
Use exact names in double quotes. Return ONLY fixed SQL.""", temperature=0.1).strip()
                    if fix_sql.startswith("```"):
                        fix_sql = fix_sql.split("```")[1].strip()
                        if fix_sql.startswith("sql"):
                            fix_sql = fix_sql[3:].strip()
                    query_result = self.action_engine.execute({"sql": fix_sql, "params": {}})
                    if query_result.get("success"):
                        rows = query_result.get("rows", [])
                        logger.info(f"  [3b] Retry success: {len(rows)} rows")
                except Exception:
                    pass

        # ─── Step 3: Build conversational answer with data ───
        t0 = time.time()
        data_section = ""
        if rows:
            data_section = f"\n\nData from database ({len(rows)} rows):\n{_json.dumps(rows[:10], indent=2, default=str)}"
            if len(rows) > 10:
                data_section += f"\n(+ {len(rows)-10} more rows)"
        elif sql:
            data_section = "\n\nThe query returned no results."

        answer_prompt = f"""You are a polite, professional AI assistant. Always address the user as "sir" or "ma'am".

The user asked: "{question}"

Conversation history:
{conversation_history if conversation_history else "None"}
{data_section}

INSTRUCTIONS:
- Start your reply with "Sure sir!" or "Here you go sir!" or "Of course sir!" etc.
- If data was found: mention SPECIFIC names, numbers, phone numbers, emails from the data
- If someone asked about a person: list their full name, phone, email, address, etc.
- If no data found: politely say "I couldn't find that in the database sir" and suggest what they can search
- Be warm, helpful, specific
- Use bullet points for multiple items
- Keep it concise but complete

Reply in plain text (no JSON):"""

        try:
            answer = llm_chat(answer_prompt, temperature=0.3)
            logger.info(f"  [4] Answer built: {round(time.time()-t0, 1)}s")
        except Exception as e:
            logger.error(f"  Answer error: {e}")
            if rows:
                answer = f"Sure sir! I found {len(rows)} records for you."
            else:
                answer = "I'm sorry sir, I had trouble processing that. Could you try rephrasing your question?"

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
