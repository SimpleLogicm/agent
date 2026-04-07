import json
import ollama as ollama_client
from config import settings


class ResponseBuilder:
    def build(self, question: str, intent: dict, query_result: dict, schema_summary: str) -> dict:
        if not query_result.get("success"):
            return {
                "answer": f"I couldn't complete that request. Error: {query_result.get('error', 'Unknown error')}",
                "suggestions": ["Try rephrasing your question", "Ask me what tables are available"],
                "data": None,
            }

        rows = query_result.get("rows", [])
        affected = query_result.get("affected_rows")

        data_summary = ""
        if rows:
            data_summary = f"Query returned {len(rows)} rows.\n"
            if len(rows) <= 10:
                data_summary += json.dumps(rows, indent=2, default=str)
            else:
                data_summary += f"First 5 rows: {json.dumps(rows[:5], indent=2, default=str)}\n... and {len(rows) - 5} more rows"
        elif affected is not None:
            data_summary = f"Operation affected {affected} rows."

        if len(schema_summary) > 2000:
            schema_summary = schema_summary[:2000]

        prompt = f"""You are a helpful AI assistant for a database. The user asked a question, and you have the query results.

Database Schema Summary:
{schema_summary}

User Question: "{question}"

Intent: {json.dumps(intent, default=str)}

Query Results:
{data_summary}

Generate a helpful, natural response that:
1. Answers the user's question clearly
2. Highlights key findings from the data
3. Provides 2-3 proactive suggestions for follow-up actions or insights

Respond ONLY with valid JSON:
{{
    "answer": "Your natural language response to the user",
    "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"]
}}"""

        try:
            response = ollama_client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = self._parse_response(response["message"]["content"])
            parsed["data"] = rows if rows else None
            return parsed
        except Exception:
            try:
                response = ollama_client.chat(
                    model=settings.OLLAMA_FALLBACK_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                )
                parsed = self._parse_response(response["message"]["content"])
                parsed["data"] = rows if rows else None
                return parsed
            except Exception:
                answer = data_summary if data_summary else "Operation completed."
                return {
                    "answer": answer,
                    "suggestions": [],
                    "data": rows if rows else None,
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
            return {"answer": text, "suggestions": []}
