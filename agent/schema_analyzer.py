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

    def build_keyword_index(self):
        """Build a keyword → table mapping for fast search."""
        self._keyword_index = {}
        for table_name, table_info in self.schema.items():
            # Extract keywords from table name
            parts = table_name.lower().replace("-", "_").split("_")
            for part in parts:
                if len(part) > 2:
                    if part not in self._keyword_index:
                        self._keyword_index[part] = set()
                    self._keyword_index[part].add(table_name)
            # Extract keywords from column names
            for col in table_info.get("columns", []):
                col_parts = col["name"].lower().replace("-", "_").split("_")
                for part in col_parts:
                    if len(part) > 2:
                        if part not in self._keyword_index:
                            self._keyword_index[part] = set()
                        self._keyword_index[part].add(table_name)

    def find_relevant_tables(self, question: str, max_tables: int = 10) -> str:
        """Find tables relevant to a question and return their detailed schema."""
        if not hasattr(self, '_keyword_index') or not self._keyword_index:
            self.build_keyword_index()

        q_lower = question.lower()
        words = [w.strip("?.,!") for w in q_lower.split() if len(w.strip("?.,!")) > 2]

        # Score tables by keyword match
        scores = {}
        for word in words:
            # Direct keyword match
            if word in self._keyword_index:
                for table in self._keyword_index[word]:
                    scores[table] = scores.get(table, 0) + 10
            # Partial match
            for keyword, tables in self._keyword_index.items():
                if word in keyword or keyword in word:
                    for table in tables:
                        scores[table] = scores.get(table, 0) + 3

        # Sort by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        relevant = [t[0] for t in ranked[:max_tables]]

        # Fallback: pick first N tables if no match
        if not relevant:
            relevant = list(self.schema.keys())[:max_tables]

        # Build clean schema for LLM
        lines = []
        for t in relevant:
            info = self.schema.get(t, {})
            cols = info.get("columns", [])
            col_details = []
            for c in cols:
                pk = " PRIMARY KEY" if c.get("primary_key") else ""
                col_details.append(f'  "{c["name"]}" {c.get("type", "TEXT")}{pk}')
            fks = info.get("foreign_keys", [])
            fk_lines = []
            for fk in fks:
                fk_lines.append(f'  FOREIGN KEY ("{", ".join(fk["columns"])}") REFERENCES "{fk["referred_table"]}"')
            lines.append(f'TABLE "{t}" (\n' + ",\n".join(col_details) + ("\n" + "\n".join(fk_lines) if fk_lines else "") + "\n)")

        return "\n\n".join(lines)

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
