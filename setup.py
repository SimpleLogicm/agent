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
        # Download Ollama Windows installer
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

            print(f"  Running installer...")
            print(f"  [NOTE] The Ollama installer window will open.")
            print(f"  Please follow the installer and wait for it to finish.")
            subprocess.run(f'start "" "{installer_path}"', shell=True)

            # Wait for user to finish installation
            print("\n  Waiting for Ollama installation to complete...")
            print("  (Press Enter after the installer finishes)")
            try:
                input()
            except EOFError:
                time.sleep(30)

            # Give Ollama time to start its service
            time.sleep(5)

            if is_ollama_running():
                print("  [OK] Ollama installed and running!")
                return True
            else:
                # Try starting it
                subprocess.run("ollama serve", shell=True, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(5)
                if is_ollama_running():
                    print("  [OK] Ollama installed and running!")
                    return True
                print("  [WARNING] Ollama installed but not running yet.")
                print("  Try restarting your terminal or computer, then run setup again.")
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
            return is_ollama_running()
        else:
            print("  Downloading Ollama for macOS...")
            ok, _ = run_cmd("curl -fsSL https://ollama.com/install.sh | sh")
            if ok:
                time.sleep(3)
                return is_ollama_running()
            print("  [WARNING] Install manually: https://ollama.com/download")
            return False

    elif system == "Linux":
        print("  Downloading Ollama for Linux...")
        ok, output = run_cmd("curl -fsSL https://ollama.com/install.sh | sh")
        if ok:
            run_cmd("ollama serve &")
            time.sleep(5)
            return is_ollama_running()
        print("  [WARNING] Install manually: https://ollama.com/download")
        return False

    else:
        print(f"  [WARNING] Unsupported OS: {system}")
        print("  Install manually: https://ollama.com/download")
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
        mac_paths = ["/usr/local/bin/ollama", os.path.expanduser("~/bin/ollama")]
        for path in mac_paths:
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
        print(f"  Using provided keys:")
        print(f"  Platform:    {platform_url}")
        print(f"  Project Key: {project_key[:15]}...")
        print(f"  API Key:     {api_key[:12]}...")
    else:
        platform_url = ask("Platform URL", DEFAULT_PLATFORM)
        project_key = ask("Project Key (pk_...)")
        api_key = ask("API Key (ak_...)")

        if not project_key or not api_key:
            print("\n  [ERROR] Project Key and API Key are required!")
            print(f"  Create a project at: {DEFAULT_PLATFORM}/dashboard\n")
            sys.exit(1)

        print("\n  Optional settings (press Enter for defaults):")
        ollama_model = ask("AI Model", "llama3.2:3b")
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

    # ─── Step 3: Write .env ───
    env_content = f"""# AI Agent SDK Configuration
# Generated by setup.py

# License (DO NOT SHARE)
PLATFORM_URL={platform_url}
PROJECT_KEY={project_key}
API_KEY={api_key}

# AI Model
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

    # ─── Done ───
    py_cmd = "python" if platform.system() == "Windows" else "python3"

    print("\n" + "=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print(f"\n  Start the agent:  {py_cmd} main.py")
    print(f"  Agent will run on: http://localhost:{agent_port}")
    print(f"  Chat demo:         http://localhost:{agent_port}/chat")
    print(f"  API docs:          http://localhost:{agent_port}/docs")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
