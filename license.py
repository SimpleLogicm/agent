import json
import os
import time
import httpx

LICENSE_FILE = ".license"
REVALIDATE_HOURS = 24


def validate(platform_url: str, project_key: str, api_key: str) -> dict:
    """Validate license with platform server. Returns license info or raises."""
    try:
        resp = httpx.post(
            f"{platform_url.rstrip('/')}/api/validate-license",
            json={"project_key": project_key, "api_key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            data["validated_at"] = time.time()
            data["platform_url"] = platform_url
            data["project_key"] = project_key
            _save_cache(data)
            return data
        elif resp.status_code == 403:
            _clear_cache()
            return {"valid": False, "error": "Invalid project key or API key"}
        else:
            return _try_cache("Platform returned unexpected status")
    except httpx.ConnectError:
        return _try_cache("Cannot reach platform server")
    except Exception as e:
        return _try_cache(str(e))


def check_license() -> dict:
    """Check if we have a valid license (cached or live)."""
    cached = _load_cache()
    if not cached:
        return {"valid": False, "error": "No license found. Run: python3 setup.py"}

    hours_since = (time.time() - cached.get("validated_at", 0)) / 3600
    if hours_since < REVALIDATE_HOURS:
        return cached

    # Re-validate
    from config import settings
    return validate(settings.PLATFORM_URL, settings.PROJECT_KEY, settings.API_KEY)


def send_heartbeat(platform_url: str, project_key: str, api_key: str, usage_count: int = 0):
    """Send usage heartbeat to platform (non-blocking, ignore failures)."""
    try:
        httpx.post(
            f"{platform_url.rstrip('/')}/api/heartbeat",
            json={
                "project_key": project_key,
                "api_key": api_key,
                "usage_count": usage_count,
                "status": "running",
            },
            timeout=5,
        )
    except Exception:
        pass


def _save_cache(data: dict):
    try:
        with open(LICENSE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _load_cache() -> dict:
    if not os.path.exists(LICENSE_FILE):
        return {}
    try:
        with open(LICENSE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _clear_cache():
    if os.path.exists(LICENSE_FILE):
        os.remove(LICENSE_FILE)


def _try_cache(error_msg: str) -> dict:
    """Fall back to cache if platform is unreachable."""
    cached = _load_cache()
    if cached and cached.get("valid"):
        hours_since = (time.time() - cached.get("validated_at", 0)) / 3600
        if hours_since < 168:  # 7 days max offline
            cached["offline_mode"] = True
            cached["offline_reason"] = error_msg
            return cached
    return {"valid": False, "error": f"License validation failed: {error_msg}"}
