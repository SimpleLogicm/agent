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
            answer = {
                "answer": "No database connected. Use POST /api/connect to connect a database first.",
                "suggestions": [
                    "Connect PostgreSQL: POST /api/connect {\"db_type\": \"postgresql\", ...}",
                    "Connect SQLite: POST /api/connect {\"db_type\": \"sqlite\", \"database\": \"path/to/db.sqlite\"}",
                    "Connect MySQL: POST /api/connect {\"db_type\": \"mysql\", ...}",
                    "Connect MongoDB: POST /api/connect {\"db_type\": \"mongodb\", ...}",
                ],
                "data": None,
            }
            self.memory.add_message(session_id, "agent", answer["answer"])
            return answer

        schema_summary = self.schema_analyzer.schema_summary
        conversation_context = self.memory.get_context_window(session_id, last_n=5)
        workflow_context = self.business_logic.get_workflow_context()
        facts_context = self.memory.get_facts_context()

        q_lower = question.lower().strip()
        tables_list = self.analysis.get("tables", [])
        total_tables = len(tables_list)

        # ─── Instant responses (no LLM needed) ───
        greetings = {"hi", "hello", "hey", "hii", "hiii", "yo", "sup", "good morning", "good evening", "good afternoon"}
        if q_lower in greetings or q_lower.rstrip("!") in greetings:
            answer = {
                "answer": f"Hello! I'm connected to your {self.analysis.get('domain', 'unknown')} database with {total_tables} tables. Ask me anything about your data!",
                "suggestions": [f"Show all tables", f"Count records in {tables_list[0]}" if tables_list else "Show schema", "What can you do?"],
                "data": None,
            }
            self.memory.add_message(session_id, "agent", answer["answer"])
            return answer

        if q_lower in ("describe", "describe database", "what is this database", "show schema", "show tables", "what tables do i have", "tables", "list tables"):
            answer = {
                "answer": f"Your database has {total_tables} tables. Domain: {self.analysis.get('domain', 'unknown')}.\n\nTables: {', '.join(tables_list[:30])}" + (f"\n... and {total_tables - 30} more" if total_tables > 30 else ""),
                "suggestions": [f"Show data from {tables_list[0]}" if tables_list else "Describe database"],
                "data": {"tables": tables_list, "domain": self.analysis.get("domain")},
            }
            self.memory.add_message(session_id, "agent", answer["answer"])
            return answer

        if q_lower.startswith("what can you do") or q_lower.startswith("help"):
            workflows = self.business_info.get("workflows", [])
            wf_list = [w["name"] for w in workflows]
            answer = {
                "answer": f"I'm connected to your {self.analysis.get('domain', '')} database ({self.db_type}). "
                          f"I can understand your data, answer questions, and perform actions. "
                          f"Detected workflows: {', '.join(wf_list) if wf_list else 'general CRUD operations'}.",
                "suggestions": self.analysis.get("available_actions", [])[:5],
                "data": {"workflows": workflows, "tables": self.analysis.get("tables", [])},
            }
            self.memory.add_message(session_id, "agent", answer["answer"])
            return answer

        # Find relevant tables
        t0 = time.time()
        relevant_schema = self.schema_analyzer.find_relevant_tables(question, max_tables=10)
        if not relevant_schema:
            relevant_schema = schema_summary[:2000]
        logger.info(f"  [1] Find tables: {round(time.time()-t0, 1)}s")

        import json as _json
        from agent.llm import chat as llm_chat

        # ─── LLM Call 1: Generate SQL ───
        t0 = time.time()
        sql_prompt = f"""You are a PostgreSQL expert. Generate a SQL query for this question.

Schema:
{relevant_schema[:2500]}

Question: "{question}"

CRITICAL RULES:
1. ALWAYS wrap table names in double quotes. Example: SELECT * FROM "Connect_connect_customers"
2. ALWAYS wrap column names in double quotes. Example: SELECT "name", "email" FROM "Connect_connect_customers"
3. Use LIMIT 20
4. Use proper JOINs with double-quoted names
5. If no SQL needed, respond with: NONE

Respond ONLY with the raw SQL query. No explanation. No markdown."""

        try:
            sql = llm_chat(sql_prompt, temperature=0.1)
            logger.info(f"  [2] SQL generated: {round(time.time()-t0, 1)}s → {sql[:80]}")
        except Exception as e:
            logger.error(f"  LLM error: {e}")
            sql = ""

        # Clean SQL
        sql = sql.strip()
        if sql.startswith("```"):
            sql = sql.split("```")[1].strip()
            if sql.startswith("sql"):
                sql = sql[3:].strip()
        if sql.upper() == "NONE" or not sql:
            sql = ""

        # ─── Execute SQL on local database (with auto-retry on error) ───
        query_result = None
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
                # Auto-retry: send error to LLM to fix the SQL
                try:
                    fix_prompt = f"""The SQL query failed with this error:
{db_error[:500]}

Original query: {sql}

Schema:
{relevant_schema[:2000]}

RULES: ALWAYS use double quotes around ALL table and column names. Example: SELECT "name" FROM "Connect_connect_customers"
Fix the query. Respond with ONLY the corrected SQL. No explanation."""
                    sql = llm_chat(fix_prompt, temperature=0.1)
                    sql = sql.strip()
                    if sql.startswith("```"):
                        sql = sql.split("```")[1].strip()
                        if sql.startswith("sql"):
                            sql = sql[3:].strip()
                    query_result = self.action_engine.execute({"sql": sql, "params": {}})
                    if query_result.get("success"):
                        rows = query_result.get("rows", [])
                        logger.info(f"  [3b] Retry success: {len(rows)} rows")
                    else:
                        logger.warning(f"  [3b] Retry also failed")
                except Exception as e:
                    logger.error(f"  [3b] Retry error: {e}")

        # ─── LLM Call 2: Generate proper conversational answer ───
        t0 = time.time()
        data_text = ""
        if rows:
            # Send max 10 rows to LLM for answer generation
            sample_rows = rows[:10]
            data_text = f"\n\nQuery returned {len(rows)} rows. Data:\n{_json.dumps(sample_rows, indent=2, default=str)}"
            if len(rows) > 10:
                data_text += f"\n... and {len(rows) - 10} more rows"
        elif query_result and not query_result.get("success"):
            data_text = f"\n\nQuery failed: {query_result.get('error', 'unknown error')}"

        answer_prompt = f"""You are a helpful AI assistant for a {self.analysis.get('domain', '')} business.
The user asked a question and here are the results from the database.

Question: "{question}"
{data_text if data_text else chr(10) + "No data found for this query."}

Give a helpful, conversational answer. Include:
1. Direct answer to the question with specific numbers/names from the data
2. Key insights or observations
3. 2-3 follow-up suggestions

Be friendly and specific. Use actual data values in your answer. Keep it concise."""

        try:
            answer_text = llm_chat(answer_prompt, temperature=0.3)
            logger.info(f"  [4] Answer built: {round(time.time()-t0, 1)}s")
        except Exception as e:
            logger.error(f"  Answer error: {e}")
            if rows:
                answer_text = f"Found {len(rows)} results for your query."
            else:
                answer_text = "I couldn't generate an answer for that question."

        # Extract suggestions from answer or generate defaults
        suggestions = []
        if tables_list:
            suggestions = [f"Tell me more about {tables_list[0]}", "Show recent records", "What insights do you have?"]

        response = {
            "answer": answer_text,
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
