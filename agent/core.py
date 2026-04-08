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

        # ─── Find relevant tables for this question ───
        t0 = time.time()
        relevant_schema = self.schema_analyzer.find_relevant_tables(question, max_tables=10)
        if not relevant_schema:
            relevant_schema = self.schema_analyzer.schema_summary[:2000]
        logger.info(f"  [1] Find tables: {round(time.time()-t0, 1)}s")

        # ─── Single smart LLM call: understand + SQL + answer ───
        t0 = time.time()
        system_prompt = f"""You are a friendly, professional AI assistant for a {domain} business. Your name is AI Agent.

PERSONALITY:
- Always greet politely: "Hello sir/ma'am!", "Sure sir!", "Of course!"
- Be conversational and warm
- Use the user's name if you know it
- Give specific answers with actual data
- If you don't find data, say so politely and suggest alternatives

DATABASE SCHEMA (use ONLY these exact table and column names in double quotes):
{relevant_schema[:2500]}

CONVERSATION HISTORY:
{conversation_history if conversation_history else "No previous messages."}

INSTRUCTIONS:
1. First understand what the user wants
2. If they need data, generate a PostgreSQL query using ONLY tables/columns from the schema above
3. ALL table and column names MUST be in double quotes: SELECT "column" FROM "table"
4. For follow-up questions like "i want full detail" or "tell me more", use context from conversation history
5. Add LIMIT 20 to queries
6. If the question is conversational (greeting, thanks, etc.), set sql to empty

Respond ONLY with valid JSON:
{{"sql": "SELECT ... or empty string if no SQL needed", "message": "your friendly response to the user"}}"""

        try:
            raw = llm_chat(f"{system_prompt}\n\nUser: {question}", temperature=0.2)
            logger.info(f"  [2] LLM response: {round(time.time()-t0, 1)}s")

            # Parse JSON
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            start_idx = raw.find("{")
            end_idx = raw.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                parsed = _json.loads(raw[start_idx:end_idx])
            else:
                parsed = {"sql": "", "message": raw}
        except Exception as e:
            logger.error(f"  LLM error: {e}")
            parsed = {"sql": "", "message": f"I'm sorry, I had trouble processing that. Could you try asking in a different way?"}

        sql = parsed.get("sql", "").strip()
        message = parsed.get("message", "")

        # Clean SQL
        if sql.startswith("```"):
            sql = sql.split("```")[1].strip()
            if sql.startswith("sql"):
                sql = sql[3:].strip()
        if sql.upper() in ("NONE", "N/A", ""):
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
                logger.warning(f"  [3] DB error, retrying: {db_error[:100]}")
                # Auto-retry
                try:
                    fix_raw = llm_chat(f"""SQL failed: {db_error[:300]}
Query: {sql}
Schema: {relevant_schema[:2000]}
Fix it. Use exact table/column names in double quotes. Return ONLY the SQL.""", temperature=0.1)
                    fix_sql = fix_raw.strip()
                    if fix_sql.startswith("```"):
                        fix_sql = fix_sql.split("```")[1].strip()
                        if fix_sql.startswith("sql"):
                            fix_sql = fix_sql[3:].strip()
                    query_result = self.action_engine.execute({"sql": fix_sql, "params": {}})
                    if query_result.get("success"):
                        rows = query_result.get("rows", [])
                        sql = fix_sql
                        logger.info(f"  [3b] Retry success: {len(rows)} rows")
                except Exception:
                    pass

        # ─── Build final answer with data ───
        if rows and not message:
            message = f"Here are the results I found - {len(rows)} records."
        elif rows:
            # LLM already gave a message, enhance with data context
            t0 = time.time()
            try:
                data_answer = llm_chat(f"""You are a friendly AI assistant. The user asked: "{question}"

Database returned {len(rows)} rows:
{_json.dumps(rows[:10], indent=2, default=str)}

Give a warm, helpful answer. Start with "Sure sir!" or "Here you go!" etc.
Mention specific names, numbers, and details from the data.
If the query was about a person, include their contact details.
Keep it conversational and informative. No JSON, just plain text.""", temperature=0.3)
                message = data_answer
                logger.info(f"  [4] Answer built: {round(time.time()-t0, 1)}s")
            except Exception:
                pass

        if not message:
            message = "I'm sorry sir/ma'am, I couldn't find relevant data for your question. Could you try rephrasing it?"

        suggestions = ["Show all customers", "Recent orders", "Top sales this month"]

        response = {
            "answer": message,
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
