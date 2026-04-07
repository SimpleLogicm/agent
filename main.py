import os
import sys
import threading
import time
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from config import settings
import license as lic


def check_setup():
    if not settings.PLATFORM_URL or not settings.PROJECT_KEY or not settings.API_KEY:
        print("\n  [ERROR] Agent not configured!")
        print("  Run: python setup.py")
        print("  Or create .env file with PLATFORM_URL, PROJECT_KEY, API_KEY\n")
        sys.exit(1)


def validate_license():
    print("  Validating license...")
    result = lic.validate(settings.PLATFORM_URL, settings.PROJECT_KEY, settings.API_KEY)

    if not result.get("valid"):
        print(f"\n  [ERROR] License validation failed: {result.get('error', 'Unknown error')}")
        print(f"  Platform: {settings.PLATFORM_URL}\n")
        sys.exit(1)

    if result.get("offline_mode"):
        print(f"  [WARNING] Offline mode: {result.get('offline_reason')}")
    else:
        print(f"  License valid: \"{result.get('project_name', 'Unknown')}\"")

    return result


def heartbeat_loop():
    while True:
        time.sleep(3600)
        try:
            lic.send_heartbeat(settings.PLATFORM_URL, settings.PROJECT_KEY, settings.API_KEY)
        except Exception:
            pass


def create_app() -> FastAPI:
    from api.routes import router, agent

    app = FastAPI(
        title="AI Agent Engine",
        description="Private AI agent running locally.",
        version="3.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    # Serve widget
    base_dir = os.path.dirname(__file__)
    widget_dir = os.path.join(base_dir, "widget")
    if os.path.isdir(widget_dir):
        app.mount("/widget", StaticFiles(directory=widget_dir), name="widget")

        @app.get("/chat", response_class=HTMLResponse)
        def chat_demo():
            with open(os.path.join(widget_dir, "demo.html"), "r") as f:
                return HTMLResponse(content=f.read())

    @app.get("/")
    def root():
        return {
            "name": "AI Agent Engine",
            "version": "3.0.0",
            "status": "running",
            "database_connected": agent.is_ready,
        }

    # Auto-check Ollama and model
    print("  Checking AI model...")
    try:
        import httpx as _httpx
        resp = _httpx.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in resp.json().get("models", [])]
        if not any(settings.OLLAMA_MODEL in m for m in models):
            print(f"  Model '{settings.OLLAMA_MODEL}' not found. Downloading...")
            import subprocess
            from setup import find_ollama_path
            ollama_cmd = find_ollama_path() or "ollama"
            subprocess.run(f"{ollama_cmd} pull {settings.OLLAMA_MODEL}", shell=True)
            print(f"  [OK] Model ready!")
        else:
            print(f"  [OK] Model '{settings.OLLAMA_MODEL}' ready")
    except Exception as e:
        print(f"  [WARNING] Ollama check failed: {e}")
        print("  Make sure Ollama is running. Chat will not work without it.")

    # Auto-connect database if configured
    db_connected = False
    if settings.DB_TYPE and settings.DB_NAME:
        print("  Connecting to database...")
        try:
            kwargs = {
                "host": settings.DB_HOST,
                "port": int(settings.DB_PORT) if settings.DB_PORT else 5432,
                "database": settings.DB_NAME,
                "user": settings.DB_USER,
                "password": settings.DB_PASSWORD,
            }
            result = agent.connect_database(db_type=settings.DB_TYPE, **kwargs)
            if result.get("status") == "connected":
                db_connected = True
                tables = result.get("tables", [])
                print(f"  [OK] Database connected!")
                print(f"  Domain:     {result.get('domain', 'unknown')}")
                print(f"  Tables:     {', '.join(tables[:5])}" + (f" (+{len(tables)-5} more)" if len(tables) > 5 else ""))
                print(f"  Workflows:  {result.get('workflows_learned', 0)} learned")
            else:
                print(f"  [WARNING] DB failed: {result.get('message', 'Unknown error')}")
        except Exception as e:
            print(f"  [WARNING] DB error: {e}")

    app.state.db_connected = db_connected
    return app


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI Agent Engine - Starting...")
    print("=" * 60)

    check_setup()
    license_info = validate_license()

    t = threading.Thread(target=heartbeat_loop, daemon=True)
    t.start()

    app = create_app()

    print("=" * 60)
    print(f"  Project:    {license_info.get('project_name', 'Unknown')}")
    print(f"  Server:     http://localhost:{settings.AGENT_PORT}")
    print(f"  Chat:       http://localhost:{settings.AGENT_PORT}/chat")
    print(f"  API Docs:   http://localhost:{settings.AGENT_PORT}/docs")
    print(f"  Model:      {settings.OLLAMA_MODEL}")
    print(f"  Database:   {'Connected' if app.state.db_connected else 'Not connected'}")
    print(f"  Privacy:    100% local - no data leaves this machine")
    print("=" * 60)
    print("  Ready! Open /chat and start asking questions.")
    print("=" * 60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=settings.AGENT_PORT)
