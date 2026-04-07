from typing import Optional, Dict, List
import ollama as ollama_client
from config import settings


class SchemaAnalyzer:
    def __init__(self):
        self.schema: dict = {}
        self.schema_summary: str = ""
        self.domain: str = ""
        self.available_actions: list[str] = []

    def analyze(self, raw_schema: dict, sample_data: Optional[Dict] = None) -> dict:
        self.schema = raw_schema
        self.schema_summary = self._build_schema_summary(raw_schema, sample_data)
        self.domain = self._detect_domain(raw_schema)
        self.available_actions = self._detect_actions(raw_schema)

        return {
            "domain": self.domain,
            "schema_summary": self.schema_summary,
            "tables": list(raw_schema.keys()),
            "available_actions": self.available_actions,
        }

    def _build_schema_summary(self, schema: dict, sample_data: Optional[Dict] = None) -> str:
        lines = []
        for table_name, table_info in schema.items():
            cols = table_info.get("columns", [])
            col_strs = []
            for c in cols:
                pk = " [PK]" if c.get("primary_key") else ""
                col_strs.append(f"  - {c['name']} ({c['type']}{pk})")

            fks = table_info.get("foreign_keys", [])
            fk_strs = []
            for fk in fks:
                fk_strs.append(
                    f"  FK: {', '.join(fk['columns'])} -> {fk['referred_table']}({', '.join(fk['referred_columns'])})"
                )

            row_count = table_info.get("row_count", "?")
            lines.append(f"Table: {table_name} ({row_count} rows)")
            lines.extend(col_strs)
            if fk_strs:
                lines.extend(fk_strs)

            if sample_data and table_name in sample_data:
                samples = sample_data[table_name]
                if samples:
                    lines.append(f"  Sample: {samples[0]}")

            lines.append("")

        return "\n".join(lines)

    def _detect_domain(self, schema: dict) -> str:
        table_names = [t.lower() for t in schema.keys()]
        all_columns = []
        for table_info in schema.values():
            for col in table_info.get("columns", []):
                all_columns.append(col["name"].lower())

        all_text = " ".join(table_names + all_columns)

        domain_hints = {
            "healthcare": ["patient", "doctor", "appointment", "diagnosis", "prescription", "medical", "clinic"],
            "e-commerce": ["product", "order", "cart", "payment", "customer", "shipping", "inventory"],
            "education": ["student", "course", "grade", "teacher", "enrollment", "class", "assignment"],
            "finance": ["account", "transaction", "balance", "ledger", "invoice", "payment"],
            "hr": ["employee", "department", "salary", "leave", "attendance", "payroll"],
            "restaurant": ["menu", "table", "reservation", "dish", "recipe", "ingredient"],
            "real_estate": ["property", "listing", "tenant", "lease", "rent", "landlord"],
            "social_media": ["post", "comment", "like", "follower", "feed", "profile"],
        }

        scores = {}
        for domain, keywords in domain_hints.items():
            score = sum(1 for kw in keywords if kw in all_text)
            if score > 0:
                scores[domain] = score

        if scores:
            return max(scores, key=scores.get)
        return "general"

    def _detect_actions(self, schema: dict) -> List[str]:
        actions = []
        for table_name in schema:
            actions.append(f"List all {table_name}")
            actions.append(f"Search {table_name}")
            actions.append(f"Get {table_name} by ID")
            actions.append(f"Count {table_name}")

            if not settings.READ_ONLY_MODE:
                actions.append(f"Add new {table_name}")
                actions.append(f"Update {table_name}")
                actions.append(f"Delete {table_name}")

        return actions

    def get_llm_analysis(self) -> str:
        prompt = f"""Analyze this database schema and provide a brief summary of:
1. What this database is for (the domain/purpose)
2. Key entities and their relationships
3. What kind of questions a user might ask

Schema:
{self.schema_summary}

Keep your response concise (under 200 words)."""

        try:
            response = ollama_client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return response["message"]["content"]
        except Exception:
            try:
                response = ollama_client.chat(
                    model=settings.OLLAMA_FALLBACK_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response["message"]["content"]
            except Exception as e:
                return f"LLM analysis unavailable: {e}"
