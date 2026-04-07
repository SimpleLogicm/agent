import json
import ollama as ollama_client
from config import settings


class IntentClassifier:
    def classify(self, question: str, schema_summary: str) -> dict:
        prompt = f"""You are an intent classifier for a database agent. Given a user's question and the database schema, classify the intent.

Database Schema:
{schema_summary}

User Question: "{question}"

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "intent": "QUERY" or "CREATE" or "UPDATE" or "DELETE" or "DESCRIBE" or "SUGGEST",
    "tables": ["list of relevant table names"],
    "entities": {{"key": "value pairs extracted from the question"}},
    "filters": {{"column": "value pairs for WHERE conditions"}},
    "description": "brief description of what the user wants"
}}

Rules:
- QUERY: user wants to read/search/list/count data
- CREATE: user wants to add/insert new data
- UPDATE: user wants to modify existing data
- DELETE: user wants to remove data
- DESCRIBE: user wants to understand the database structure
- SUGGEST: user wants recommendations or suggestions
- Extract specific values mentioned (names, dates, numbers, etc.) into entities
- Put filter conditions into filters"""

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
                return {
                    "intent": "QUERY",
                    "tables": [],
                    "entities": {},
                    "filters": {},
                    "description": question,
                    "error": str(e),
                }

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
            return {
                "intent": "QUERY",
                "tables": [],
                "entities": {},
                "filters": {},
                "description": text,
            }
