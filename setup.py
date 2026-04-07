#!/usr/bin/env python3
"""
Interactive setup for AI Agent SDK.

Usage:
  python3 setup.py                          (interactive)
  python3 setup.py --pk pk_xxx --ak ak_xxx  (non-interactive)
"""

import os
import sys
import platform
import subprocess
import argparse
import time


def ask(prompt, default=""):
    try:
        val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
        return val or default
    except EOFError:
        return default


def run_cmd(cmd, check=False):
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def is_ollama_running():
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def get_ollama_models():
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        models = resp.json().get("models", [])
        return [m["name"] for m in models]
    except Exception:
        return []


def install_ollama():
    """Install Ollama on any platform."""
    system = platform.system()
    print("\n  Installing Ollama (free local AI engine)...")

    if system == "Windows":
        print("  Downloading Ollama for Windows...")
        try:
            import httpx
            url = "https://ollama.com/download/OllamaSetup.exe"
            installer_path = os.path.join(os.environ.get("TEMP", "."), "OllamaSetup.exe")

            print(f"  Downloading from {url}...")
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(installer_path, "wb") as f:
                    for chunk in response.iter_bytes(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            print(f"\r  Downloading... {pct}%", end="", flush=True)
                print(f"\r  Download complete!          ")

            # Silent install - no popups, no clicks needed
            print("  Installing silently (no popups)...")
            result = subprocess.run(
                f'"{installer_path}" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES',
                shell=True, timeout=120, capture_output=True,
            )

            # Wait for Ollama service to start
            print("  Waiting for Ollama to start...")
            for i in range(12):
                time.sleep(5)
                if is_ollama_running():
                    print("  [OK] Ollama installed and running!")
                    return True

            # Try starting manually
            ollama_exe = find_ollama_path()
            if ollama_exe:
                subprocess.Popen(f'{ollama_exe} serve', shell=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(5)
                if is_ollama_running():
                    print("  [OK] Ollama installed and running!")
                    return True

            print("  [WARNING] Ollama installed but not running yet.")
            print("  Restart your terminal, then run setup again.")
            return False

        except Exception as e:
            print(f"  [ERROR] Auto-install failed: {e}")
            print("  Please install manually from: https://ollama.com/download")
            return False

    elif system == "Darwin":  # macOS
        if os.path.exists("/Applications/Ollama.app"):
            print("  Ollama app found. Starting it...")
            subprocess.run("open /Applications/Ollama.app", shell=True)
            time.sleep(5)
            if is_ollama_running():
                print("  [OK] Ollama is running!")
                return True

        # Try installing via official script
        print("  Downloading Ollama for macOS...")
        try:
            import httpx
            url = "https://ollama.com/download/Ollama-darwin.zip"
            zip_path = "/tmp/Ollama-darwin.zip"

            print(f"  Downloading from {url}...")
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in response.iter_bytes(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            print(f"\r  Downloading... {pct}%", end="", flush=True)
            print(f"\r  Download complete!          ")

            # Unzip and move to Applications
            print("  Installing to /Applications...")
            run_cmd("unzip -o /tmp/Ollama-darwin.zip -d /Applications/")
            time.sleep(2)

            if os.path.exists("/Applications/Ollama.app"):
                print("  Starting Ollama...")
                subprocess.run("open /Applications/Ollama.app", shell=True)
                time.sleep(5)
                if is_ollama_running():
                    print("  [OK] Ollama installed and running!")
                    return True

        except Exception as e:
            print(f"  Download failed: {e}")

        # Fallback to curl script
        print("  Trying alternative install method...")
        ok, _ = run_cmd("curl -fsSL https://ollama.com/install.sh | sh")
        if ok:
            time.sleep(3)
            if is_ollama_running():
                print("  [OK] Ollama installed and running!")
                return True
            # Try starting it
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(5)
            if is_ollama_running():
                print("  [OK] Ollama installed and running!")
                return True

        print("  [WARNING] Could not auto-install Ollama.")
        print("  Install manually: https://ollama.com/download")
        print("  After installing, run: ollama serve")
        return False

    elif system == "Linux":
        print("  Downloading Ollama for Linux...")
        print("  Running: curl -fsSL https://ollama.com/install.sh | sh")
        print("  (This may ask for sudo password)")

        # Try with sudo
        ok, output = run_cmd("curl -fsSL https://ollama.com/install.sh | sh")
        if not ok:
            # Try without sudo wrapper
            ok, output = run_cmd("curl -fsSL https://ollama.com/install.sh | bash")

        if ok:
            print("  [OK] Ollama installed!")
            # Start ollama service
            print("  Starting Ollama service...")

            # Try systemd first
            run_cmd("sudo systemctl start ollama 2>/dev/null")
            time.sleep(3)

            if is_ollama_running():
                print("  [OK] Ollama is running!")
                return True

            # Try direct start
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(5)

            if is_ollama_running():
                print("  [OK] Ollama is running!")
                return True

            # Try with nohup
            run_cmd("nohup ollama serve > /dev/null 2>&1 &")
            time.sleep(5)

            if is_ollama_running():
                print("  [OK] Ollama is running!")
                return True

            print("  [WARNING] Ollama installed but could not start automatically.")
            print("  Run in a separate terminal: ollama serve")
            return False
        else:
            print("  [WARNING] Could not auto-install Ollama.")
            print("  Install manually:")
            print("    curl -fsSL https://ollama.com/install.sh | sh")
            print("  Then start: ollama serve")
            return False

    else:
        print(f"  [WARNING] Unsupported OS: {system}")
        print("  Install Ollama manually: https://ollama.com/download")
        return False


def find_ollama_path():
    """Find ollama executable path, especially on Windows where PATH may not be updated."""
    # Try direct command first
    try:
        result = subprocess.run("ollama --version", shell=True, capture_output=True, timeout=5)
        if result.returncode == 0:
            return "ollama"
    except Exception:
        pass

    # Windows-specific paths
    if platform.system() == "Windows":
        home = os.path.expanduser("~")
        possible_paths = [
            os.path.join(home, "AppData", "Local", "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Ollama", "ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
        ]
        for path in possible_paths:
            if path and os.path.exists(path):
                return f'"{path}"'

    # macOS
    if platform.system() == "Darwin":
        mac_paths = [
            "/usr/local/bin/ollama",
            os.path.expanduser("~/bin/ollama"),
            "/opt/homebrew/bin/ollama",
        ]
        for path in mac_paths:
            if os.path.exists(path):
                return path

    # Linux
    if platform.system() == "Linux":
        linux_paths = [
            "/usr/local/bin/ollama",
            "/usr/bin/ollama",
            os.path.expanduser("~/bin/ollama"),
            "/snap/bin/ollama",
        ]
        for path in linux_paths:
            if os.path.exists(path):
                return path

    return None


def pull_model(model_name):
    """Pull an AI model via Ollama."""
    print(f"\n  Downloading AI model '{model_name}' (~2GB, one-time)...")
    print("  This may take a few minutes...")

    ollama_cmd = find_ollama_path()
    if not ollama_cmd:
        print(f"  [WARNING] Cannot find ollama executable.")
        print(f"  Please restart your terminal and run: ollama pull {model_name}")
        return False

    try:
        result = subprocess.run(
            f"{ollama_cmd} pull {model_name}",
            shell=True, timeout=600,
            capture_output=False,
        )
        if result.returncode == 0:
            print(f"  [OK] Model '{model_name}' ready!")
            return True
        else:
            print(f"  [WARNING] Failed to pull model.")
            print(f"  Restart your terminal and run: ollama pull {model_name}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [WARNING] Download timed out. Run: ollama pull {model_name}")
        return False
    except Exception as e:
        print(f"  [WARNING] Error: {e}")
        print(f"  Restart your terminal and run: ollama pull {model_name}")
        return False


def main():
    parser = argparse.ArgumentParser(description="AI Agent SDK Setup")
    parser.add_argument("--platform", default="", help="Platform URL")
    parser.add_argument("--pk", default="", help="Project Key")
    parser.add_argument("--ak", default="", help="API Key")
    parser.add_argument("--model", default="", help="Ollama model")
    parser.add_argument("--port", default="", help="Agent port")
    parser.add_argument("--skip-ollama", action="store_true", help="Skip Ollama install")
    parser.add_argument("--llm", default="", help="LLM provider: groq or ollama")
    parser.add_argument("--groq-key", default="", help="Groq API key (free from console.groq.com)")
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
    print("  You need your Project Key and API Key from the platform.")
    print(f"  Get them at: {DEFAULT_PLATFORM}/dashboard")
    print("=" * 60 + "\n")

    # ─── Step 1: Get license keys ───
    if args.pk and args.ak:
        platform_url = args.platform or DEFAULT_PLATFORM
        project_key = args.pk
        api_key = args.ak
        ollama_model = args.model or "llama3.2:3b"
        agent_port = args.port or "8000"
        llm_provider = args.llm or "groq"
        groq_api_key = args.groq_key or ""
        print(f"  Using provided keys:")
        print(f"  Platform:    {platform_url}")
        print(f"  Project Key: {project_key[:15]}...")
        print(f"  API Key:     {api_key[:12]}...")
        print(f"  LLM:         {llm_provider}")
    else:
        platform_url = ask("Platform URL", DEFAULT_PLATFORM)
        project_key = ask("Project Key (pk_...)")
        api_key = ask("API Key (ak_...)")

        if not project_key or not api_key:
            print("\n  [ERROR] Project Key and API Key are required!")
            print(f"  Create a project at: {DEFAULT_PLATFORM}/dashboard\n")
            sys.exit(1)

        print("\n  ─── AI Provider ───")
        print("  groq   = Fast (1-2 sec), free, questions go to cloud")
        print("  ollama = Slower (15-60 sec), 100% offline")
        llm_provider = ask("AI Provider", "groq")

        groq_api_key = ""
        if llm_provider == "groq":
            print("\n  Get your FREE Groq key at: https://console.groq.com/keys")
            groq_api_key = ask("Groq API Key")
            if not groq_api_key:
                print("  No Groq key provided. Will use Ollama (slower).")
                llm_provider = "ollama"

        print("\n  Optional settings (press Enter for defaults):")
        ollama_model = ask("Ollama Model (fallback)", "llama3.2:3b")
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
            print(f"\n  [ERROR] Invalid keys! Server said: {resp.text}")
            print(f"  Check your keys at: {DEFAULT_PLATFORM}/dashboard\n")
            sys.exit(1)
    except Exception as e:
        print(f"\n  [WARNING] Cannot reach platform: {e}")
        print("  Continuing with offline setup.\n")

    # ─── Step 3: Database configuration ───
    print("\n  ─── Database Configuration ───")
    print("  Connect your database so the agent can access it on startup.\n")

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
        print(f"\n  [OK] Database configured: {db_type}://{db_host or 'file'}:{db_port or ''}/{db_name}")
    else:
        print("\n  [SKIP] No database configured. You can connect later via API.")

    # ─── Step 4: Write .env ───
    env_content = f"""# AI Agent SDK Configuration
# Generated by setup.py

# License (DO NOT SHARE)
PLATFORM_URL={platform_url}
PROJECT_KEY={project_key}
API_KEY={api_key}

# Database (auto-connect on startup)
DB_TYPE={db_type}
DB_HOST={db_host}
DB_PORT={db_port}
DB_NAME={db_name}
DB_USER={db_user}
DB_PASSWORD={db_password}

# AI Provider: groq (fast, free) or ollama (slow, offline)
LLM_PROVIDER={llm_provider}
GROQ_API_KEY={groq_api_key}
GROQ_MODEL=llama-3.1-8b-instant

# Ollama (fallback / offline mode)
OLLAMA_MODEL={ollama_model}
OLLAMA_FALLBACK_MODEL=mistral

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

    # ─── Step 4: Install Ollama if needed ───
    if not args.skip_ollama:
        print("\n  Checking Ollama...")
        if is_ollama_running():
            print("  [OK] Ollama is running")
            models = get_ollama_models()
            if any(ollama_model in m for m in models):
                print(f"  [OK] Model '{ollama_model}' is ready")
            else:
                print(f"  Model '{ollama_model}' not found. Downloading...")
                pull_model(ollama_model)
        else:
            print("  Ollama not found. Installing...")
            installed = install_ollama()
            if installed:
                models = get_ollama_models()
                if not any(ollama_model in m for m in models):
                    pull_model(ollama_model)
            else:
                print(f"\n  [!] Install Ollama manually: https://ollama.com/download")
                print(f"  Then run: ollama pull {ollama_model}")

    # ─── Step 5: Auto-start the agent ───
    py_cmd = "python" if platform.system() == "Windows" else "python3"

    print("\n" + "=" * 60)
    print("  Setup Complete! Starting agent...")
    print("=" * 60 + "\n")

    os.execvp(sys.executable, [sys.executable, "main.py"])


if __name__ == "__main__":
    main()
