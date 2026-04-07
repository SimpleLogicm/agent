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
        if q_lower in ("describe", "describe database", "what is this database", "show schema", "show tables", "what tables do i have"):
            llm_analysis = self.schema_analyzer.get_llm_analysis()
            answer = {
                "answer": llm_analysis,
                "suggestions": self.analysis.get("available_actions", [])[:5],
                "data": {"tables": self.analysis["tables"], "domain": self.analysis["domain"]},
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

        # Find only relevant tables for this question
        t0 = time.time()
        relevant_schema = self.schema_analyzer.find_relevant_tables(question, max_tables=10)
        if not relevant_schema:
            relevant_schema = schema_summary[:2000]
        logger.info(f"  [1] Find tables: {round(time.time()-t0, 1)}s")

        # SINGLE LLM call - generate SQL directly (skip intent + response builder)
        t0 = time.time()
        import json as _json
        import ollama as _ollama
        fast_prompt = f"""You are a database assistant. Given the schema and question, generate a SQL query and a short answer.

Schema:
{relevant_schema[:2500]}

Question: "{question}"

Respond ONLY with valid JSON:
{{"sql": "SELECT ...", "answer": "short natural language answer", "suggestions": ["suggestion1", "suggestion2"]}}

Rules:
- Generate valid PostgreSQL SQL
- Use LIMIT 20
- If question is greeting (hi/hello), respond with: {{"sql": "", "answer": "Hello! I'm connected to your database. Ask me anything about your data.", "suggestions": ["Show all tables", "Count records"]}}"""

        try:
            llm_resp = _ollama.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": fast_prompt}],
                options={"temperature": 0.1},
            )
            raw = llm_resp["message"]["content"].strip()
            logger.info(f"  [2] LLM response: {round(time.time()-t0, 1)}s")

            # Parse JSON from LLM
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            start_idx = raw.find("{")
            end_idx = raw.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                parsed = _json.loads(raw[start_idx:end_idx])
            else:
                parsed = {"sql": "", "answer": raw, "suggestions": []}
        except Exception as e:
            logger.error(f"  LLM error: {e}")
            parsed = {"sql": "", "answer": f"Error processing your question: {e}", "suggestions": []}

        sql = parsed.get("sql", "")
        answer_text = parsed.get("answer", "")
        suggestions = parsed.get("suggestions", [])

        # Execute SQL if generated
        query_result = None
        if sql and sql.strip().upper().startswith("SELECT"):
            t0 = time.time()
            query_info = {"sql": sql, "params": {}}
            query_result = self.action_engine.execute(query_info)
            logger.info(f"  [3] DB execute: {round(time.time()-t0, 1)}s → {query_result.get('row_count', 0)} rows")

            if query_result.get("success") and query_result.get("rows"):
                rows = query_result["rows"]
                if not answer_text or answer_text == "short natural language answer":
                    answer_text = f"Found {len(rows)} results."
        elif sql:
            query_info = {"sql": sql, "params": {}}
            query_result = self.action_engine.execute(query_info)

        response = {
            "answer": answer_text or "I processed your question but couldn't generate a response.",
            "suggestions": suggestions if isinstance(suggestions, list) else [],
            "data": query_result.get("rows") if query_result and query_result.get("success") else None,
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
