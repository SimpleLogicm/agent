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
    """Verify license keys are configured."""
    if not settings.PLATFORM_URL or not settings.PROJECT_KEY or not settings.API_KEY:
        print("\n  [ERROR] Agent not configured!")
        print("  Run: python3 setup.py")
        print("  Or create .env file with PLATFORM_URL, PROJECT_KEY, API_KEY\n")
        sys.exit(1)


def validate_license():
    """Validate license with platform."""
    print("  Validating license...")
    result = lic.validate(settings.PLATFORM_URL, settings.PROJECT_KEY, settings.API_KEY)

    if not result.get("valid"):
        print(f"\n  [ERROR] License validation failed: {result.get('error', 'Unknown error')}")
        print("  Check your Project Key and API Key on the platform dashboard.")
        print(f"  Platform: {settings.PLATFORM_URL}\n")
        sys.exit(1)

    if result.get("offline_mode"):
        print(f"  [WARNING] Running in offline mode: {result.get('offline_reason')}")
        print(f"  Last validated successfully. Will retry later.")
    else:
        print(f"  License valid: \"{result.get('project_name', 'Unknown')}\"")

    return result


def heartbeat_loop():
    """Send periodic heartbeat to platform."""
    while True:
        time.sleep(3600)  # Every hour
        try:
            lic.send_heartbeat(settings.PLATFORM_URL, settings.PROJECT_KEY, settings.API_KEY)
        except Exception:
            pass


def create_app() -> FastAPI:
    from api.routes import router

    app = FastAPI(
        title="AI Agent Engine",
        description="Private AI agent running locally. Licensed via AI Agent Platform.",
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
            "docs": f"http://localhost:{settings.AGENT_PORT}/docs",
            "chat": f"http://localhost:{settings.AGENT_PORT}/chat",
            "endpoints": {
                "POST /api/connect": "Connect to a database",
                "POST /api/ask": "Ask a question",
                "GET  /api/schema": "View schema",
                "GET  /api/health": "Health check",
            },
        }

    return app


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI Agent Engine - Starting...")
    print("=" * 60)

    check_setup()
    license_info = validate_license()

    # Start heartbeat in background
    t = threading.Thread(target=heartbeat_loop, daemon=True)
    t.start()

    app = create_app()

    # Auto-connect database if configured in .env
    db_connected = False
    if settings.DB_TYPE and settings.DB_NAME:
        print("  Connecting to database...")
        from api.routes import agent
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
                domain = result.get("domain", "unknown")
                tables = result.get("tables", [])
                print(f"  [OK] Database connected!")
                print(f"  Domain:     {domain}")
                print(f"  Tables:     {', '.join(tables[:5])}" + (f" (+{len(tables)-5} more)" if len(tables) > 5 else ""))
                print(f"  Workflows:  {result.get('workflows_learned', 0)} learned")
            else:
                print(f"  [WARNING] Database connection failed: {result.get('message', 'Unknown error')}")
                print("  Agent will start without database. Connect manually via API.")
        except Exception as e:
            print(f"  [WARNING] Database connection error: {e}")
            print("  Agent will start without database. Connect manually via API.")

    print("=" * 60)
    project_name = license_info.get("project_name", "Unknown")
    print(f"  Project:    {project_name}")
    print(f"  Server:     http://localhost:{settings.AGENT_PORT}")
    print(f"  Chat:       http://localhost:{settings.AGENT_PORT}/chat")
    print(f"  API Docs:   http://localhost:{settings.AGENT_PORT}/docs")
    print(f"  Model:      {settings.OLLAMA_MODEL}")
    print(f"  Database:   {'Connected' if db_connected else 'Not connected (use /api/connect)'}")
    print(f"  Privacy:    100% local - no data leaves this machine")
    print("=" * 60)
    if db_connected:
        print("  Ready! Open /chat and start asking questions.")
    else:
        print("  Ready! Connect a database first, then start asking questions.")
    print("=" * 60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=settings.AGENT_PORT)
