import time
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from agent.core import AgentCore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent")

router = APIRouter()
agent = AgentCore()


class ConnectDBRequest(BaseModel):
    db_type: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    user: str = ""
    password: str = ""
    uri: Optional[str] = None


class ConnectAPIRequest(BaseModel):
    base_url: str
    headers: Optional[Dict[str, str]] = None
    openapi_url: Optional[str] = None


class AnalyzeCodeRequest(BaseModel):
    project_path: str


class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


@router.get("/health")
def health():
    return {
        "status": "running",
        "database_connected": agent.is_ready,
        "db_type": agent.db_type if agent.is_ready else None,
        "domain": agent.analysis.get("domain") if agent.is_ready else None,
    }


@router.post("/connect")
def connect_database(req: ConnectDBRequest):
    kwargs = {"host": req.host, "port": req.port, "database": req.database, "user": req.user, "password": req.password}
    if req.uri:
        kwargs["uri"] = req.uri
    result = agent.connect_database(db_type=req.db_type, **kwargs)
    if result["status"] != "connected":
        raise HTTPException(status_code=400, detail=result.get("message", "Connection failed"))
    return result


@router.post("/connect-api")
def connect_api(req: ConnectAPIRequest):
    result = agent.connect_api(base_url=req.base_url, headers=req.headers, openapi_url=req.openapi_url)
    if result["status"] != "connected":
        raise HTTPException(status_code=400, detail=result.get("message", "API connection failed"))
    return result


@router.post("/analyze")
def analyze_codebase(req: AnalyzeCodeRequest):
    result = agent.analyze_codebase(req.project_path)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/disconnect")
def disconnect():
    agent.disconnect()
    return {"status": "disconnected"}


@router.post("/ask")
def ask_question(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    logger.info(f"Question: {req.question}")
    start = time.time()
    result = agent.ask(req.question, session_id=req.session_id)
    elapsed = round(time.time() - start, 1)
    logger.info(f"Answer ({elapsed}s): {result.get('answer', '')[:100]}")
    return result


@router.get("/schema")
def get_schema():
    schema = agent.get_schema()
    if "error" in schema:
        raise HTTPException(status_code=400, detail=schema["error"])
    return schema


@router.get("/workflows")
def get_workflows():
    return {
        "domain": agent.business_logic.domain,
        "workflows": agent.business_info.get("workflows", []),
    }
