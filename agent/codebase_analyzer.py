import os
import re
from typing import List, Dict, Any, Optional
import ollama as ollama_client
from config import settings


FRAMEWORK_PATTERNS = {
    "django": {
        "files": ["manage.py", "wsgi.py", "asgi.py", "settings.py"],
        "imports": ["django", "from django"],
        "extensions": [".py"],
    },
    "flask": {
        "files": ["app.py", "wsgi.py"],
        "imports": ["flask", "from flask"],
        "extensions": [".py"],
    },
    "fastapi": {
        "files": ["main.py"],
        "imports": ["fastapi", "from fastapi"],
        "extensions": [".py"],
    },
    "express": {
        "files": ["app.js", "server.js", "index.js", "package.json"],
        "imports": ["express", "require('express')", "require(\"express\")"],
        "extensions": [".js", ".ts"],
    },
    "nextjs": {
        "files": ["next.config.js", "next.config.ts", "next.config.mjs"],
        "imports": ["next"],
        "extensions": [".js", ".ts", ".tsx", ".jsx"],
    },
    "rails": {
        "files": ["Gemfile", "config.ru", "Rakefile"],
        "imports": ["rails", "ActiveRecord"],
        "extensions": [".rb"],
    },
    "spring": {
        "files": ["pom.xml", "build.gradle"],
        "imports": ["springframework", "SpringBootApplication"],
        "extensions": [".java", ".kt"],
    },
    "laravel": {
        "files": ["artisan", "composer.json"],
        "imports": ["Illuminate", "Laravel"],
        "extensions": [".php"],
    },
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".rb",
    ".php", ".go", ".rs", ".cs", ".swift", ".dart",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".idea", ".vscode", "dist", "build", ".next", "vendor",
    "target", ".gradle", "Pods", ".dart_tool",
}

MAX_FILE_SIZE = 100_000  # 100KB


class CodebaseAnalyzer:
    def __init__(self):
        self.project_path: str = ""
        self.framework: str = "unknown"
        self.language: str = "unknown"
        self.routes: List[Dict[str, str]] = []
        self.models: List[Dict[str, Any]] = []
        self.files_scanned: int = 0
        self.summary: str = ""

    def analyze(self, project_path: str) -> Dict[str, Any]:
        self.project_path = os.path.abspath(project_path)
        if not os.path.isdir(self.project_path):
            return {"error": f"Directory not found: {self.project_path}"}

        self.framework = self._detect_framework()
        self.language = self._detect_language()

        code_files = self._scan_files()
        self.files_scanned = len(code_files)

        self.routes = self._extract_routes(code_files)
        self.models = self._extract_models(code_files)

        self.summary = self._build_summary(code_files)

        return {
            "project_path": self.project_path,
            "framework": self.framework,
            "language": self.language,
            "files_scanned": self.files_scanned,
            "routes_found": len(self.routes),
            "models_found": len(self.models),
            "routes": self.routes[:30],
            "models": self.models[:20],
        }

    def _detect_framework(self) -> str:
        for fw_name, fw_info in FRAMEWORK_PATTERNS.items():
            for f in fw_info["files"]:
                if os.path.exists(os.path.join(self.project_path, f)):
                    return fw_name

        for fw_name, fw_info in FRAMEWORK_PATTERNS.items():
            for root, dirs, files in os.walk(self.project_path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for fname in files[:50]:
                    ext = os.path.splitext(fname)[1]
                    if ext in fw_info["extensions"]:
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, "r", errors="ignore") as fh:
                                content = fh.read(5000)
                                for imp in fw_info["imports"]:
                                    if imp in content:
                                        return fw_name
                        except Exception:
                            continue
                break
        return "unknown"

    def _detect_language(self) -> str:
        ext_count: Dict[str, int] = {}
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1]
                if ext in CODE_EXTENSIONS:
                    ext_count[ext] = ext_count.get(ext, 0) + 1

        if not ext_count:
            return "unknown"

        ext_to_lang = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
            ".kt": "kotlin", ".rb": "ruby", ".php": "php", ".go": "go",
            ".rs": "rust", ".cs": "csharp", ".swift": "swift", ".dart": "dart",
        }
        top_ext = max(ext_count, key=ext_count.get)
        return ext_to_lang.get(top_ext, "unknown")

    def _scan_files(self) -> List[Dict[str, str]]:
        files = []
        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                if ext not in CODE_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                if os.path.getsize(fpath) > MAX_FILE_SIZE:
                    continue
                try:
                    with open(fpath, "r", errors="ignore") as fh:
                        content = fh.read()
                    rel_path = os.path.relpath(fpath, self.project_path)
                    files.append({"path": rel_path, "content": content})
                except Exception:
                    continue

                if len(files) >= 200:
                    return files
        return files

    def _extract_routes(self, code_files: List[Dict]) -> List[Dict[str, str]]:
        routes = []
        route_patterns = [
            # Python: Flask/FastAPI
            r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)',
            # Python: Django urls
            r'path\s*\(\s*["\']([^"\']+)["\'].*?name\s*=\s*["\']([^"\']+)',
            # Express.js
            r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)',
            # Generic route decorator
            r'@(?:route|api_view)\s*\(\s*["\']([^"\']+)',
        ]

        for f in code_files:
            for pattern in route_patterns:
                matches = re.findall(pattern, f["content"])
                for match in matches:
                    if isinstance(match, tuple):
                        if len(match) == 2:
                            routes.append({"method": match[0].upper(), "path": match[1], "file": f["path"]})
                    else:
                        routes.append({"method": "ANY", "path": match, "file": f["path"]})
        return routes

    def _extract_models(self, code_files: List[Dict]) -> List[Dict[str, Any]]:
        models = []
        model_patterns = [
            # Django/SQLAlchemy models
            r'class\s+(\w+)\s*\((?:models\.Model|db\.Model|Base|DeclarativeBase)',
            # Mongoose schemas
            r'(?:new\s+)?(?:mongoose\.)?Schema\s*\(\s*\{',
            # TypeORM/Prisma
            r'@Entity\s*\(\s*\)\s*(?:export\s+)?class\s+(\w+)',
            # Generic class with common DB field patterns
            r'class\s+(\w+).*?(?:CharField|IntegerField|TextField|Column|Field)',
        ]

        for f in code_files:
            for pattern in model_patterns:
                matches = re.findall(pattern, f["content"])
                for match in matches:
                    if match:
                        models.append({"name": match, "file": f["path"]})
        return models

    def _build_summary(self, code_files: List[Dict]) -> str:
        lines = [
            f"Project: {os.path.basename(self.project_path)}",
            f"Framework: {self.framework}",
            f"Language: {self.language}",
            f"Files Scanned: {self.files_scanned}",
            f"Routes Found: {len(self.routes)}",
            f"Models Found: {len(self.models)}",
            "",
        ]

        if self.routes:
            lines.append("Routes:")
            for r in self.routes[:15]:
                lines.append(f"  {r.get('method', 'ANY')} {r['path']} ({r['file']})")
            lines.append("")

        if self.models:
            lines.append("Models:")
            for m in self.models[:10]:
                lines.append(f"  {m['name']} ({m['file']})")
            lines.append("")

        return "\n".join(lines)

    def get_llm_analysis(self) -> str:
        prompt = f"""Analyze this codebase and describe:
1. What this project does
2. Key functionality and features
3. What kind of questions or tasks an AI agent could help with

Codebase Info:
{self.summary}

Keep response under 200 words."""

        try:
            response = ollama_client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return response["message"]["content"]
        except Exception as e:
            return f"LLM analysis unavailable: {e}"
