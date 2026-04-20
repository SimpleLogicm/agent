#!/usr/bin/env python3
"""
Interactive setup for AI Agent SDK.

Usage:
  python3 setup.py                                        (interactive)
  python3 setup.py --pk pk_xxx --ak ak_xxx --gemini XXX   (non-interactive)
"""

import os
import sys
import platform
import argparse


def ask(prompt, default=""):
    try:
        val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
        return val or default
    except EOFError:
        return default


def main():
    parser = argparse.ArgumentParser(description="AI Agent SDK Setup")
    parser.add_argument("--platform", default="", help="Platform URL")
    parser.add_argument("--pk", default="", help="Project Key")
    parser.add_argument("--ak", default="", help="API Key")
    parser.add_argument("--gemini", default="", help="Gemini API Key (get free from https://aistudio.google.com/apikey)")
    parser.add_argument("--port", default="", help="Agent port")
    parser.add_argument("--db-type", default="", help="Database type: postgresql, mysql, mongodb, sqlite")
    parser.add_argument("--db-host", default="", help="Database host")
    parser.add_argument("--db-port", default="", help="Database port")
    parser.add_argument("--db-name", default="", help="Database name")
    parser.add_argument("--db-user", default="", help="Database user")
    parser.add_argument("--db-password", default="", help="Database password")
    args = parser.parse_args()

    DEFAULT_PLATFORM = "https://agent-web-cdrs.onrender.com"

    print("\n" + "=" * 60)
    print("  AI Agent SDK - Setup")
    print("=" * 60)
    print("  Project keys from: " + DEFAULT_PLATFORM + "/dashboard")
    print("  Gemini API key from: https://aistudio.google.com/apikey (FREE)")
    print("=" * 60 + "\n")

    # ─── Step 1: Platform keys ───
    if args.pk and args.ak:
        platform_url = args.platform or DEFAULT_PLATFORM
        project_key = args.pk
        api_key = args.ak
        gemini_key = args.gemini
        agent_port = args.port or "8000"
        print(f"  Platform:    {platform_url}")
        print(f"  Project Key: {project_key[:15]}...")
        print(f"  API Key:     {api_key[:12]}...")
        if gemini_key:
            print(f"  Gemini Key:  {gemini_key[:10]}...")
    else:
        platform_url = ask("Platform URL", DEFAULT_PLATFORM)
        project_key = ask("Project Key (pk_...)")
        api_key = ask("API Key (ak_...)")

        if not project_key or not api_key:
            print("\n  [ERROR] Project Key and API Key are required!")
            print(f"  Create a project at: {DEFAULT_PLATFORM}/dashboard\n")
            sys.exit(1)

        print("\n  Get your FREE Gemini API key at: https://aistudio.google.com/apikey")
        gemini_key = ask("Gemini API Key")

        if not gemini_key:
            print("\n  [ERROR] Gemini API key is required!")
            print("  Get it free at: https://aistudio.google.com/apikey\n")
            sys.exit(1)

        agent_port = ask("Agent Port", "8000")

    # ─── Step 2: Validate license ───
    print("\n  Validating license...")
    try:
        import httpx
        resp = httpx.post(
            f"{platform_url.rstrip('/')}/api/validate-license",
            json={"project_key": project_key, "api_key": api_key},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"  [OK] License VALID: \"{data.get('project_name', 'Unknown')}\"")
        else:
            print(f"\n  [ERROR] Invalid keys! {resp.text}")
            print(f"  Check keys at: {DEFAULT_PLATFORM}/dashboard\n")
            sys.exit(1)
    except Exception as e:
        print(f"\n  [WARNING] Cannot reach platform: {e}")
        print("  Continuing with offline setup.\n")

    # ─── Step 3: Database configuration ───
    print("\n  ─── Database Configuration ───")
    if args.db_type:
        db_type = args.db_type
        db_host = args.db_host or "localhost"
        db_port = args.db_port or ("5432" if db_type == "postgresql" else "3306" if db_type == "mysql" else "27017" if db_type == "mongodb" else "")
        db_name = args.db_name or ""
        db_user = args.db_user or ""
        db_password = args.db_password or ""
    else:
        print("  Supported: postgresql, mysql, mongodb, sqlite")
        db_type = ask("Database type", "postgresql")

        if db_type == "sqlite":
            db_name = ask("Database file path (e.g., ./mydata.db)")
            db_host = ""
            db_port = ""
            db_user = ""
            db_password = ""
        else:
            default_port = "5432" if db_type == "postgresql" else "3306" if db_type == "mysql" else "27017"
            db_host = ask("Database host", "localhost")
            db_port = ask("Database port", default_port)
            db_name = ask("Database name")
            db_user = ask("Database user", "postgres" if db_type == "postgresql" else "root")
            db_password = ask("Database password")

    if db_name:
        print(f"\n  [OK] Database: {db_type}://{db_host}:{db_port}/{db_name}")
    else:
        print("\n  [SKIP] No database configured.")

    # ─── Step 4: Write .env ───
    env_content = f"""# AI Agent SDK Configuration
# Generated by setup.py

# License (DO NOT SHARE)
PLATFORM_URL={platform_url}
PROJECT_KEY={project_key}
API_KEY={api_key}

# Gemini AI (get free from https://aistudio.google.com/apikey)
GEMINI_API_KEY={gemini_key}
GEMINI_MODEL=gemini-2.0-flash

# Database
DB_TYPE={db_type}
DB_HOST={db_host}
DB_PORT={db_port}
DB_NAME={db_name}
DB_USER={db_user}
DB_PASSWORD={db_password}

# Agent Server
AGENT_PORT={agent_port}

# Safety
READ_ONLY_MODE=false
MAX_RESULT_ROWS=100
BLOCKED_TABLES=
"""
    with open(".env", "w") as f:
        f.write(env_content)
    print("\n  [OK] Created .env configuration file")

    # ─── Step 5: Test Gemini ───
    if gemini_key:
        print("\n  Testing Gemini AI...")
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents="Say OK if you can read this.",
            )
            if resp.text:
                print(f"  [OK] Gemini AI working!")
        except Exception as e:
            print(f"  [WARNING] Gemini test failed: {e}")
            print("  Check your API key at https://aistudio.google.com/apikey")

    # ─── Done ───
    py_cmd = "python" if platform.system() == "Windows" else "python3"

    print("\n" + "=" * 60)
    print("  Setup Complete! Starting agent...")
    print("=" * 60 + "\n")

    os.execvp(sys.executable, [sys.executable, "main.py"])


if __name__ == "__main__":
    main()
