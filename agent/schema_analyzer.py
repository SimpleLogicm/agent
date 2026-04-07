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
            col_names = [c['name'] for c in cols]
            lines.append(f"{table_name}: {', '.join(col_names)}")

        return "\n".join(lines)

    def get_table_detail(self, table_name: str) -> str:
        """Get detailed schema for specific tables (used when answering questions)."""
        if table_name not in self.schema:
            return ""
        table_info = self.schema[table_name]
        lines = [f"Table: {table_name}"]
        for c in table_info.get("columns", []):
            pk = " [PK]" if c.get("primary_key") else ""
            lines.append(f"  - {c['name']} ({c['type']}{pk})")
        for fk in table_info.get("foreign_keys", []):
            lines.append(f"  FK: {', '.join(fk['columns'])} -> {fk['referred_table']}({', '.join(fk['referred_columns'])})")
        return "\n".join(lines)

    def find_relevant_tables(self, question: str, max_tables: int = 15) -> str:
        """Find tables relevant to a question and return their detailed schema."""
        q_lower = question.lower()
        scored = []
        for table_name in self.schema:
            score = 0
            t_lower = table_name.lower().replace("_", " ")
            # Check if any word in question matches table name
            for word in q_lower.split():
                if len(word) > 2 and word in t_lower:
                    score += 10
            # Check column names
            for col in self.schema[table_name].get("columns", []):
                col_lower = col["name"].lower().replace("_", " ")
                for word in q_lower.split():
                    if len(word) > 2 and word in col_lower:
                        score += 5
            # Boost tables with more rows (likely important)
            row_count = self.schema[table_name].get("row_count", 0)
            if row_count > 100:
                score += 2
            if row_count > 1000:
                score += 3
            if score > 0:
                scored.append((table_name, score))

        # Sort by relevance
        scored.sort(key=lambda x: x[1], reverse=True)
        relevant = [t[0] for t in scored[:max_tables]]

        # If no match found, return top tables by row count
        if not relevant:
            by_rows = sorted(self.schema.items(), key=lambda x: x[1].get("row_count", 0), reverse=True)
            relevant = [t[0] for t in by_rows[:max_tables]]

        details = []
        for t in relevant:
            details.append(self.get_table_detail(t))
        return "\n\n".join(details)

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
