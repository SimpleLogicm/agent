import uuid
from typing import Optional, Dict, Any
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

        raw_schema = self.connector.get_full_schema()

        sample_data = {}
        for table_name in raw_schema:
            if table_name not in settings.BLOCKED_TABLES:
                try:
                    sample_data[table_name] = self.connector.get_sample_data(
                        table_name, settings.SAMPLE_ROWS_FOR_CONTEXT
                    )
                except Exception:
                    sample_data[table_name] = []

        self.analysis = self.schema_analyzer.analyze(raw_schema, sample_data)

        self.business_info = self.business_logic.learn(
            domain=self.analysis.get("domain", "general"),
            schema=raw_schema,
        )

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

        enhanced_context = schema_summary
        if conversation_context:
            enhanced_context += f"\n\n{conversation_context}"
        if workflow_context:
            enhanced_context += f"\n\n{workflow_context}"
        if facts_context:
            enhanced_context += f"\n\n{facts_context}"

        if self.api_connector.is_connected:
            enhanced_context += f"\n\nAvailable API:\n{self.api_connector.get_endpoints_summary()}"

        intent = self.intent_classifier.classify(question, enhanced_context)

        query_info = self.query_generator.generate(intent, schema_summary)

        if query_info.get("error") or not query_info.get("sql"):
            answer = {
                "answer": f"I understood your question but couldn't generate a query. {query_info.get('error', '')}",
                "suggestions": ["Try rephrasing", "Ask 'what tables do I have?' to see available data"],
                "data": None,
            }
            self.memory.add_message(session_id, "agent", answer["answer"])
            return answer

        query_result = self.action_engine.execute(query_info)

        response = self.response_builder.build(question, intent, query_result, enhanced_context)

        self.memory.add_message(session_id, "agent", response.get("answer", ""),
                                metadata={"intent": intent.get("intent"), "sql": query_info.get("sql")})

        response["debug"] = {
            "intent": intent,
            "sql": query_info.get("sql", ""),
            "sql_explanation": query_info.get("explanation", ""),
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
