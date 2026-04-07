import json
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

import httpx


class APIConnector:
    """Connects to existing REST APIs and discovers available endpoints."""

    def __init__(self):
        self.base_url: str = ""
        self.endpoints: List[Dict[str, Any]] = []
        self.headers: Dict[str, str] = {}
        self.is_connected: bool = False

    def connect(self, base_url: str, headers: Optional[Dict[str, str]] = None,
                openapi_url: Optional[str] = None, endpoints: Optional[List[Dict]] = None) -> Dict[str, Any]:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

        try:
            if openapi_url:
                self._discover_from_openapi(openapi_url)
            elif endpoints:
                self.endpoints = endpoints
            else:
                self._try_auto_discover()

            self.is_connected = True
            return {
                "status": "connected",
                "base_url": self.base_url,
                "endpoints_found": len(self.endpoints),
                "endpoints": [{"method": e.get("method"), "path": e.get("path"), "description": e.get("description", "")} for e in self.endpoints[:20]],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def disconnect(self):
        self.base_url = ""
        self.endpoints = []
        self.is_connected = False

    def _discover_from_openapi(self, openapi_url: str):
        resp = httpx.get(openapi_url, timeout=10)
        spec = resp.json()

        self.endpoints = []
        paths = spec.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    params = []
                    for p in details.get("parameters", []):
                        params.append({
                            "name": p.get("name"),
                            "in": p.get("in"),
                            "required": p.get("required", False),
                            "type": p.get("schema", {}).get("type", "string"),
                        })

                    body_schema = {}
                    req_body = details.get("requestBody", {})
                    if req_body:
                        content = req_body.get("content", {})
                        json_content = content.get("application/json", {})
                        body_schema = json_content.get("schema", {})

                    self.endpoints.append({
                        "path": path,
                        "method": method.upper(),
                        "description": details.get("summary", details.get("description", "")),
                        "parameters": params,
                        "body_schema": body_schema,
                        "tags": details.get("tags", []),
                    })

    def _try_auto_discover(self):
        common_paths = [
            "/openapi.json", "/swagger.json", "/api/openapi.json",
            "/docs/openapi.json", "/api-docs",
        ]
        for path in common_paths:
            try:
                url = urljoin(self.base_url, path)
                resp = httpx.get(url, headers=self.headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if "paths" in data or "openapi" in data or "swagger" in data:
                        self._discover_from_openapi(url)
                        return
            except Exception:
                continue

        self.endpoints = []

    def call_endpoint(self, method: str, path: str, params: Optional[Dict] = None,
                      body: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=30) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=body,
                )
                try:
                    data = response.json()
                except Exception:
                    data = response.text

                return {
                    "success": response.status_code < 400,
                    "status_code": response.status_code,
                    "data": data,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_endpoints_summary(self) -> str:
        if not self.endpoints:
            return "No API endpoints discovered."

        lines = [f"API Base URL: {self.base_url}", f"Total Endpoints: {len(self.endpoints)}", ""]
        for ep in self.endpoints:
            desc = ep.get("description", "")
            params_str = ""
            if ep.get("parameters"):
                param_names = [p["name"] for p in ep["parameters"]]
                params_str = f" (params: {', '.join(param_names)})"
            lines.append(f"  {ep['method']} {ep['path']}{params_str} - {desc}")

        return "\n".join(lines)
