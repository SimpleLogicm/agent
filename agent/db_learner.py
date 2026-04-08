"""
DB Learner - Analyzes the database ONCE on connect and creates a smart map.
Saves locally so it doesn't need to re-learn on restart.

The map tells the agent:
- What each table is for (customers, orders, users, etc.)
- Which tables are related
- What category each table belongs to
- Which table to use for common questions
"""

import os
import json
import logging
import time
from typing import Dict, List, Any

logger = logging.getLogger("agent")

DB_MAP_FILE = "db_map.json"


class DBLearner:
    def __init__(self):
        self.db_map: Dict[str, Any] = {}
        self.category_tables: Dict[str, List[str]] = {}
        self.table_purposes: Dict[str, str] = {}

    def learn(self, schema: Dict[str, Any], llm_chat_fn, force: bool = False) -> Dict:
        """Learn the database structure. Uses LLM to understand table purposes."""

        # Check if we already have a saved map
        if not force and os.path.exists(DB_MAP_FILE):
            saved = self._load_map()
            if saved and len(saved.get("table_purposes", {})) > 0:
                self.db_map = saved
                self.table_purposes = saved.get("table_purposes", {})
                self.category_tables = saved.get("category_tables", {})
                logger.info(f"  Loaded saved DB map ({len(self.table_purposes)} tables mapped)")
                return self.db_map

        logger.info(f"  Learning database structure ({len(schema)} tables)...")

        # Build compact table list for LLM
        table_summaries = []
        for table_name, table_info in schema.items():
            cols = [c["name"] for c in table_info.get("columns", [])]
            # Only send first 10 columns to keep prompt small
            col_str = ", ".join(cols[:10])
            if len(cols) > 10:
                col_str += f" (+{len(cols)-10} more)"
            table_summaries.append(f"{table_name}: {col_str}")

        # Split into chunks if too many tables (LLM has context limit)
        chunk_size = 50
        all_purposes = {}
        all_categories = {}

        for i in range(0, len(table_summaries), chunk_size):
            chunk = table_summaries[i:i + chunk_size]
            chunk_text = "\n".join(chunk)

            prompt = f"""Analyze these database tables and categorize them.

TABLES:
{chunk_text}

For each table, respond with a JSON object:
{{
  "table_purposes": {{
    "table_name": "one line description of what this table stores"
  }},
  "categories": {{
    "customers": ["table1", "table2"],
    "orders": ["table3"],
    "products": ["table4"],
    "users": ["table5"],
    "attendance": ["table6"],
    "finance": ["table7"],
    "settings": ["table8"],
    "logs": ["table9"]
  }}
}}

RULES:
- Every table must have a purpose
- Categories: customers, orders, products, users, employees, attendance, finance, payments, invoices, inventory, settings, logs, notifications, reports, other
- A table can be in multiple categories
- Use the EXACT table name as-is
- Respond ONLY with JSON, no explanation"""

            try:
                raw = llm_chat_fn(prompt, temperature=0.1)
                parsed = self._parse_json(raw)
                if parsed:
                    purposes = parsed.get("table_purposes", {})
                    categories = parsed.get("categories", {})
                    all_purposes.update(purposes)
                    for cat, tables in categories.items():
                        if cat not in all_categories:
                            all_categories[cat] = []
                        all_categories[cat].extend(tables)
            except Exception as e:
                logger.warning(f"  DB learn chunk failed: {e}")

        # If LLM failed, build basic map from table names
        if not all_purposes:
            all_purposes, all_categories = self._build_basic_map(schema)

        self.table_purposes = all_purposes
        self.category_tables = all_categories
        self.db_map = {
            "table_purposes": all_purposes,
            "category_tables": all_categories,
            "learned_at": time.time(),
            "total_tables": len(schema),
        }

        # Save locally
        self._save_map(self.db_map)
        logger.info(f"  DB map learned: {len(all_purposes)} tables, {len(all_categories)} categories")

        return self.db_map

    def find_tables_for_question(self, question: str, schema: Dict, max_tables: int = 5) -> List[str]:
        """Find the best tables to query for a given question."""
        q_lower = question.lower()

        # Step 1: Match by category
        category_keywords = {
            "customers": ["customer", "client", "buyer", "consumer", "contact"],
            "orders": ["order", "purchase", "buy", "sale", "transaction", "deal"],
            "products": ["product", "item", "goods", "inventory", "stock", "catalog"],
            "users": ["user", "login", "account", "profile", "employee", "staff", "team"],
            "employees": ["employee", "staff", "team", "worker", "member", "hr"],
            "attendance": ["attendance", "check-in", "check-out", "present", "absent", "leave", "working hours"],
            "finance": ["finance", "payment", "invoice", "billing", "amount", "revenue", "expense", "salary"],
            "payments": ["payment", "pay", "transaction", "receipt", "refund"],
            "invoices": ["invoice", "bill", "receipt"],
            "reports": ["report", "analytics", "dashboard", "insight", "summary", "statistics"],
            "notifications": ["notification", "alert", "message", "email", "sms"],
        }

        matched_categories = set()
        for cat, keywords in category_keywords.items():
            for kw in keywords:
                if kw in q_lower:
                    matched_categories.add(cat)

        # Get tables from matched categories
        candidate_tables = set()
        for cat in matched_categories:
            for table in self.category_tables.get(cat, []):
                if table in schema:
                    candidate_tables.add(table)

        # Step 2: Match by person/entity name (search across customer/user tables)
        # If question mentions a name, prioritize customer and user tables
        common_data_words = {"show", "tell", "find", "get", "list", "how", "many", "count", "what", "who", "where", "all", "me", "about", "the", "is", "are", "my", "our", "do", "have", "i", "want", "need", "please", "sir", "maam"}
        question_words = set(q_lower.replace("'", "").replace("?", "").replace(".", "").split())
        name_words = question_words - common_data_words

        if name_words and not matched_categories:
            # Likely searching for a person/entity
            for cat in ["customers", "users", "employees"]:
                for table in self.category_tables.get(cat, []):
                    if table in schema:
                        candidate_tables.add(table)

        # Step 3: Direct table name matching (keyword in table name)
        for table_name in schema:
            t_lower = table_name.lower()
            for word in q_lower.split():
                if len(word) > 3 and word in t_lower:
                    candidate_tables.add(table_name)

        # Step 4: If still nothing, use purpose descriptions
        if not candidate_tables:
            for table_name, purpose in self.table_purposes.items():
                if table_name not in schema:
                    continue
                purpose_lower = purpose.lower()
                for word in q_lower.split():
                    if len(word) > 3 and word in purpose_lower:
                        candidate_tables.add(table_name)

        # Step 5: Fallback - top tables from main categories
        if not candidate_tables:
            for cat in ["customers", "orders", "users", "products"]:
                for table in self.category_tables.get(cat, [])[:2]:
                    if table in schema:
                        candidate_tables.add(table)

        return list(candidate_tables)[:max_tables]

    def get_context_for_question(self, question: str, schema: Dict) -> str:
        """Get the relevant schema context for a question - ready to send to LLM."""
        tables = self.find_tables_for_question(question, schema)

        if not tables:
            return ""

        lines = []
        for t in tables:
            info = schema.get(t, {})
            cols = info.get("columns", [])
            col_details = []
            for c in cols:
                pk = " PRIMARY KEY" if c.get("primary_key") else ""
                col_details.append(f'  "{c["name"]}" {c.get("type", "TEXT")}{pk}')
            fks = info.get("foreign_keys", [])
            fk_lines = []
            for fk in fks:
                fk_lines.append(f'  FOREIGN KEY ("{", ".join(fk["columns"])}") REFERENCES "{fk["referred_table"]}"')

            purpose = self.table_purposes.get(t, "")
            purpose_line = f" -- {purpose}" if purpose else ""
            lines.append(f'TABLE "{t}"{purpose_line} (\n' + ",\n".join(col_details) + ("\n" + "\n".join(fk_lines) if fk_lines else "") + "\n)")

        return "\n\n".join(lines)

    def _build_basic_map(self, schema: Dict) -> tuple:
        """Fallback: build map from table names without LLM."""
        purposes = {}
        categories = {}

        keyword_to_category = {
            "customer": "customers", "client": "customers", "buyer": "customers",
            "order": "orders", "sale": "orders", "purchase": "orders",
            "product": "products", "item": "products", "catalog": "products",
            "user": "users", "auth": "users", "login": "users", "account": "users",
            "employee": "employees", "staff": "employees", "hr": "employees",
            "attend": "attendance", "leave": "attendance",
            "payment": "payments", "pay": "payments", "invoice": "invoices",
            "finance": "finance", "salary": "finance", "expense": "finance",
            "log": "logs", "audit": "logs", "history": "logs",
            "notification": "notifications", "alert": "notifications",
            "setting": "settings", "config": "settings",
            "report": "reports",
        }

        for table_name in schema:
            t_lower = table_name.lower()
            purposes[table_name] = f"Table: {table_name}"

            for keyword, category in keyword_to_category.items():
                if keyword in t_lower:
                    if category not in categories:
                        categories[category] = []
                    if table_name not in categories[category]:
                        categories[category].append(table_name)

        return purposes, categories

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {}

    def _save_map(self, data: dict):
        try:
            with open(DB_MAP_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_map(self) -> dict:
        try:
            with open(DB_MAP_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
