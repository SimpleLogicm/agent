"""
DB Brain - The agent's deep understanding of the database.

On first connect:
  1. Reads ALL tables, columns, foreign keys
  2. Reads SAMPLE DATA from key tables
  3. Builds a complete knowledge document (like a human reading a manual)
  4. Saves this "brain" locally as db_brain.json

On every question:
  The brain already knows:
  - What each table stores (with examples)
  - Which table to use for customers, orders, users, etc.
  - Actual names/values in the database
  - How tables relate to each other
"""

import os
import json
import logging
import time
from typing import Dict, List, Any, Optional

logger = logging.getLogger("agent")

BRAIN_FILE = "db_brain.json"


class DBBrain:
    def __init__(self):
        self.knowledge: str = ""        # Full understanding text
        self.table_map: Dict = {}       # category → [tables]
        self.table_info: Dict = {}      # table → {purpose, key_columns, sample_values}
        self.relationships: List = []    # [{from, to, via}]
        self.summary: str = ""          # One-paragraph summary of the whole DB

    def learn(self, schema: Dict, connector, llm_chat_fn, force: bool = False) -> Dict:
        """Build deep understanding of the database."""

        # Check saved brain
        if not force and os.path.exists(BRAIN_FILE):
            saved = self._load()
            if saved and saved.get("knowledge"):
                self.knowledge = saved["knowledge"]
                self.table_map = saved.get("table_map", {})
                self.table_info = saved.get("table_info", {})
                self.relationships = saved.get("relationships", [])
                self.summary = saved.get("summary", "")
                logger.info(f"  Loaded brain from file ({len(self.table_info)} tables understood)")
                return saved

        logger.info(f"  Building brain for {len(schema)} tables...")
        logger.info(f"  Step 1/3: Reading table structure...")

        # ─── Step 1: Build compact schema description ───
        table_descriptions = []
        for table_name, info in schema.items():
            cols = info.get("columns", [])
            col_names = [c["name"] for c in cols]
            fks = info.get("foreign_keys", [])
            fk_text = ""
            if fks:
                fk_parts = [f'{fk["columns"][0]}→{fk["referred_table"]}' for fk in fks if fk.get("columns")]
                fk_text = f" | FK: {', '.join(fk_parts)}"
            table_descriptions.append(f"{table_name}: {', '.join(col_names[:12])}{fk_text}")

        # ─── Step 2: Read sample data from tables that look important ───
        logger.info(f"  Step 2/3: Reading sample data from key tables...")
        sample_data_text = []
        important_keywords = ["customer", "user", "order", "product", "client", "employee", "sale", "payment", "invoice", "contact", "lead"]

        sampled_tables = []
        for table_name in schema:
            t_lower = table_name.lower()
            if any(kw in t_lower for kw in important_keywords):
                sampled_tables.append(table_name)
        # Also add first few tables if none matched
        if not sampled_tables:
            sampled_tables = list(schema.keys())[:10]
        # Limit to 20 tables for sampling
        sampled_tables = sampled_tables[:20]

        for table_name in sampled_tables:
            try:
                rows = connector.get_sample_data(table_name, limit=3)
                if rows:
                    sample_data_text.append(f"Sample from {table_name}: {json.dumps(rows[:2], default=str)[:500]}")
            except Exception:
                pass

        # ─── Step 3: Send everything to LLM to build understanding ───
        logger.info(f"  Step 3/3: AI is analyzing the database...")

        # Split tables into chunks for LLM
        all_tables_text = "\n".join(table_descriptions)

        # Chunk if too large
        if len(all_tables_text) > 6000:
            chunks = []
            current = ""
            for line in table_descriptions:
                if len(current) + len(line) > 5000:
                    chunks.append(current)
                    current = line + "\n"
                else:
                    current += line + "\n"
            if current:
                chunks.append(current)
        else:
            chunks = [all_tables_text]

        # Process each chunk
        all_analysis = []
        for i, chunk in enumerate(chunks):
            prompt = f"""You are analyzing a database to build a complete understanding. Study these tables carefully.

TABLES (batch {i+1}/{len(chunks)}):
{chunk}

{chr(10).join(sample_data_text[:10]) if i == 0 else ""}

Respond with JSON:
{{
  "table_map": {{
    "customers": ["exact_table_name1"],
    "orders": ["exact_table_name2"],
    "products": ["exact_table_name3"],
    "users": ["exact_table_name4"],
    "employees": ["exact_table_name5"],
    "attendance": ["exact_table_name6"],
    "payments": ["exact_table_name7"],
    "leads": ["exact_table_name8"],
    "contacts": ["exact_table_name9"],
    "settings": ["exact_table_name10"]
  }},
  "table_info": {{
    "exact_table_name": {{
      "purpose": "what this table stores",
      "search_columns": ["name", "email", "phone"],
      "display_columns": ["name", "email", "phone", "company"]
    }}
  }}
}}

RULES:
- Use EXACT table names as they appear above
- table_map: group tables by what they represent
- table_info: for each important table, list which columns to search and display
- Only include tables that exist in the list above
- Respond ONLY with JSON"""

            try:
                raw = llm_chat_fn(prompt, temperature=0.1)
                parsed = self._parse_json(raw)
                if parsed:
                    all_analysis.append(parsed)
            except Exception as e:
                logger.warning(f"  Chunk {i+1} analysis failed: {e}")

        # Merge all analysis
        merged_map = {}
        merged_info = {}
        for analysis in all_analysis:
            for cat, tables in analysis.get("table_map", {}).items():
                if cat not in merged_map:
                    merged_map[cat] = []
                merged_map[cat].extend(tables)
            merged_info.update(analysis.get("table_info", {}))

        # Fallback if LLM failed
        if not merged_map:
            merged_map, merged_info = self._basic_analysis(schema)

        # Build the knowledge document
        knowledge_parts = [f"DATABASE KNOWLEDGE (learned from {len(schema)} tables)\n"]

        # Summary
        categories = [f"{cat}: {len(tables)} tables" for cat, tables in merged_map.items() if tables]
        knowledge_parts.append(f"Categories: {', '.join(categories)}\n")

        # Table details
        for cat, tables in merged_map.items():
            if not tables:
                continue
            knowledge_parts.append(f"\n=== {cat.upper()} ===")
            for t in tables:
                info = merged_info.get(t, {})
                purpose = info.get("purpose", "")
                search_cols = info.get("search_columns", [])
                display_cols = info.get("display_columns", [])
                knowledge_parts.append(f'  Table: "{t}"')
                if purpose:
                    knowledge_parts.append(f"    Purpose: {purpose}")
                if search_cols:
                    knowledge_parts.append(f'    Search by: {", ".join(search_cols)}')
                if display_cols:
                    knowledge_parts.append(f'    Show: {", ".join(display_cols)}')

        self.knowledge = "\n".join(knowledge_parts)
        self.table_map = merged_map
        self.table_info = merged_info
        self.relationships = []

        # Save brain
        brain_data = {
            "knowledge": self.knowledge,
            "table_map": self.table_map,
            "table_info": self.table_info,
            "relationships": self.relationships,
            "summary": self.summary,
            "learned_at": time.time(),
            "total_tables": len(schema),
        }
        self._save(brain_data)
        logger.info(f"  Brain built: {len(merged_info)} tables understood, {len(merged_map)} categories")

        return brain_data

    def get_context(self, question: str, schema: Dict) -> str:
        """Get everything the LLM needs to answer this question correctly."""

        # Find relevant tables
        tables = self._find_tables(question, schema)

        # Build precise schema for these tables
        context_parts = []

        # Add the relevant knowledge
        if self.knowledge:
            context_parts.append("YOUR KNOWLEDGE ABOUT THIS DATABASE:")
            context_parts.append(self.knowledge[:1500])
            context_parts.append("")

        # Add exact schema for relevant tables
        context_parts.append("TABLES TO USE (exact schema):")
        for t in tables:
            info = schema.get(t, {})
            cols = info.get("columns", [])
            col_lines = []
            for c in cols:
                pk = " PRIMARY KEY" if c.get("primary_key") else ""
                col_lines.append(f'  "{c["name"]}" {c.get("type", "TEXT")}{pk}')
            fks = info.get("foreign_keys", [])
            fk_lines = [f'  FK "{fk["columns"][0]}" → "{fk["referred_table"]}"' for fk in fks if fk.get("columns")]

            # Add purpose
            tinfo = self.table_info.get(t, {})
            purpose = tinfo.get("purpose", "")
            purpose_text = f" -- {purpose}" if purpose else ""

            context_parts.append(f'TABLE "{t}"{purpose_text} (')
            context_parts.append(",\n".join(col_lines))
            if fk_lines:
                context_parts.extend(fk_lines)
            context_parts.append(")")
            context_parts.append("")

        return "\n".join(context_parts)

    def _find_tables(self, question: str, schema: Dict, max_tables: int = 5) -> List[str]:
        """Find the right tables for a question using the brain's knowledge."""
        q_lower = question.lower()
        candidates = set()

        # 1. Category matching
        cat_keywords = {
            "customers": ["customer", "client", "buyer", "contact", "lead"],
            "orders": ["order", "purchase", "sale", "deal", "transaction", "buy"],
            "products": ["product", "item", "goods", "stock", "inventory", "catalog"],
            "users": ["user", "login", "account", "profile", "staff", "team", "member"],
            "employees": ["employee", "staff", "worker", "team", "member", "hr"],
            "attendance": ["attendance", "check-in", "checkin", "present", "absent", "leave", "working"],
            "payments": ["payment", "pay", "invoice", "bill", "receipt", "refund", "amount"],
            "leads": ["lead", "prospect", "inquiry", "enquiry"],
            "contacts": ["contact", "phone", "mobile", "number", "email", "address"],
        }

        matched_cats = set()
        for cat, keywords in cat_keywords.items():
            for kw in keywords:
                if kw in q_lower:
                    matched_cats.add(cat)

        for cat in matched_cats:
            for table in self.table_map.get(cat, []):
                if table in schema:
                    candidates.add(table)

        # 2. Person name search → check customer/user/employee/contact tables
        stop_words = {"show", "tell", "find", "get", "list", "how", "many", "count", "what", "who",
                       "where", "all", "me", "about", "the", "is", "are", "my", "our", "do", "have",
                       "i", "want", "need", "please", "sir", "maam", "top", "recent", "new", "old",
                       "total", "much", "give", "muze", "mujhe", "ka", "ki", "ke", "hai", "kya",
                       "kitne", "kitna", "batao", "dikhao", "chahiye", "number", "naam", "name"}
        words = set(q_lower.replace("'", "").replace("?", "").replace(".", "").replace(",", "").split())
        potential_names = words - stop_words

        if potential_names and not matched_cats:
            # Probably searching for a person
            for cat in ["customers", "users", "employees", "contacts", "leads"]:
                for table in self.table_map.get(cat, []):
                    if table in schema:
                        candidates.add(table)

        # 3. Search by table_info purpose
        if not candidates:
            for table, info in self.table_info.items():
                if table not in schema:
                    continue
                purpose = info.get("purpose", "").lower()
                for word in q_lower.split():
                    if len(word) > 3 and word in purpose:
                        candidates.add(table)

        # 4. Fallback
        if not candidates:
            for cat in ["customers", "orders", "users"]:
                for table in self.table_map.get(cat, [])[:2]:
                    if table in schema:
                        candidates.add(table)

        return list(candidates)[:max_tables]

    def get_search_hint(self, question: str) -> str:
        """Get search hints for the SQL generator."""
        q_lower = question.lower()
        stop_words = {"show", "tell", "find", "get", "list", "how", "many", "count", "what", "who",
                       "where", "all", "me", "about", "the", "is", "are", "my", "our", "do", "have",
                       "i", "want", "need", "please", "sir", "maam", "top", "recent", "ka", "ki",
                       "kitne", "batao", "dikhao", "chahiye", "number", "naam", "name", "full", "detail"}
        words = set(q_lower.replace("'", "").replace("?", "").replace(".", "").replace(",", "").split())
        names = words - stop_words
        names = [n for n in names if len(n) > 2]

        if names:
            return f"User is likely searching for: {', '.join(names)}. Use ILIKE '%name%' for fuzzy matching."
        return ""

    def _basic_analysis(self, schema: Dict) -> tuple:
        """Fallback analysis without LLM."""
        table_map = {}
        table_info = {}
        kw_to_cat = {
            "customer": "customers", "client": "customers", "buyer": "customers",
            "order": "orders", "sale": "orders",
            "product": "products", "item": "products",
            "user": "users", "auth": "users",
            "employee": "employees", "staff": "employees",
            "attend": "attendance",
            "payment": "payments", "invoice": "payments",
            "lead": "leads", "contact": "contacts",
        }
        for table in schema:
            t_lower = table.lower()
            for kw, cat in kw_to_cat.items():
                if kw in t_lower:
                    if cat not in table_map:
                        table_map[cat] = []
                    table_map[cat].append(table)
            cols = [c["name"] for c in schema[table].get("columns", [])]
            table_info[table] = {"purpose": table, "search_columns": cols[:5], "display_columns": cols[:8]}
        return table_map, table_info

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

    def _save(self, data: dict):
        try:
            with open(BRAIN_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load(self) -> dict:
        try:
            with open(BRAIN_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
