import json
import ollama as ollama_client
from config import settings


class QueryGenerator:
    def generate(self, intent: dict, schema_summary: str) -> dict:
        prompt = f"""You are a PostgreSQL query generator. Generate a safe SQL query based on the user's intent and database schema.

Database Schema:
{schema_summary}

User Intent:
{json.dumps(intent, indent=2)}

Rules:
1. Generate ONLY safe, parameterized SQL
2. Use :param_name for parameters (SQLAlchemy style)
3. NEVER use DROP, TRUNCATE, ALTER, CREATE TABLE, or GRANT
4. For SELECT queries, always add LIMIT {settings.MAX_RESULT_ROWS}
5. Use proper JOINs based on foreign keys
6. Use double quotes around table/column names if they contain special chars

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "sql": "the SQL query with :param placeholders",
    "params": {{"param_name": "value"}},
    "explanation": "brief explanation of what this query does"
}}"""

        try:
            response = ollama_client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            return self._parse_response(response["message"]["content"])
        except Exception:
            try:
                response = ollama_client.chat(
                    model=settings.OLLAMA_FALLBACK_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1},
                )
                return self._parse_response(response["message"]["content"])
            except Exception as e:
                return {"sql": "", "params": {}, "explanation": "", "error": str(e)}

    def _parse_response(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"sql": "", "params": {}, "explanation": text}
