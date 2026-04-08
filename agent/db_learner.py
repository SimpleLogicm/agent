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
                self.people_search_tables = saved.get("people_search_tables", [])
                self.relationships = saved.get("relationships", [])
                self.summary = saved.get("summary", "")
                logger.info(f"  Loaded brain ({len(self.table_info)} tables, {len(self.people_search_tables)} people tables)")
                return saved

        logger.info(f"  Building brain for {len(schema)} tables...")

        # ─── Step 1: Auto-categorize ALL tables by keywords ───
        logger.info(f"  Step 1/3: Categorizing tables...")
        merged_map, merged_info = self._basic_analysis(schema)

        # ─── Step 2: Deep scan - read actual data from important tables ───
        logger.info(f"  Step 2/3: Deep scanning tables (reading actual data)...")

        # Find ALL tables that could contain people/business data
        people_tables = set()
        for cat in ["customers", "users", "employees", "contacts", "leads"]:
            for t in merged_map.get(cat, []):
                people_tables.add(t)

        # Scan ALL tables in the database for person-name columns
        # No hardcoded table names - purely based on column structure
        self.people_search_tables = []
        scanned = 0

        for table_name, info in schema.items():
            try:
                cols = info.get("columns", [])

                # Look at every column: is it a TEXT/VARCHAR that could hold a person's name?
                searchable_cols = []
                display_cols = []

                for col in cols:
                    c_name = col["name"]
                    c_lower = c_name.lower()
                    c_type = col.get("type", "").upper()
                    is_text = any(t in c_type for t in ["VARCHAR", "TEXT", "CHAR"])

                    if not is_text:
                        continue

                    # Check if column name contains any word that means "name of a person"
                    name_words = c_lower.replace("_", " ").split()
                    has_name_indicator = False
                    for w in name_words:
                        if w in ("name", "first", "last", "username", "full"):
                            has_name_indicator = True
                            break

                    if has_name_indicator:
                        # Exclude columns that are clearly not person names
                        not_person = ("table_name", "file_name", "task_name", "module_name",
                                      "category_name", "subcategory_name", "activity_name",
                                      "product_name", "scheme_name", "report_name",
                                      "field_name", "column_name", "app_name", "model_name",
                                      "permission_name", "group_name", "content_type",
                                      "sku_name", "brand_name", "bank_name", "branch_name",
                                      "hotel_name", "shop_name", "city_name", "state_name",
                                      "country_name", "document_name")
                        if c_lower not in not_person:
                            searchable_cols.append(c_name)

                    # Display columns (any useful info)
                    display_words = ("name", "email", "mobile", "phone", "address",
                                     "company", "city", "status", "username", "designation")
                    if any(w in c_lower for w in display_words):
                        display_cols.append(c_name)

                if not searchable_cols:
                    continue

                # Verify this table has actual data
                scanned += 1
                row_count = 0
                sample_name = ""
                try:
                    row_count = connector.get_row_count(table_name)
                    if row_count > 0:
                        rows = connector.get_sample_data(table_name, limit=1)
                        if rows:
                            for sc in searchable_cols:
                                val = rows[0].get(sc)
                                if val and isinstance(val, str) and len(val) > 1:
                                    sample_name = val
                                    break
                except Exception:
                    pass

                # Only include tables that have data
                if row_count > 0:
                    self.people_search_tables.append({
                        "table": table_name,
                        "search_columns": searchable_cols,
                        "display_columns": display_cols[:10],
                        "row_count": row_count,
                        "sample_names": [sample_name] if sample_name else [],
                    })

                merged_info[table_name]["search_columns"] = searchable_cols
                merged_info[table_name]["display_columns"] = display_cols[:10]
                merged_info[table_name]["row_count"] = row_count

            except Exception:
                pass

        # Sort by row count (tables with most data first - more likely to have the person)
        self.people_search_tables.sort(key=lambda x: x.get("row_count", 0), reverse=True)
        logger.info(f"  Deep scanned {scanned} tables, {len(self.people_search_tables)} have searchable people data")

        # ─── Step 3: ONE LLM call for uncategorized tables ───
        logger.info(f"  Step 3/3: Finalizing...")
        try:
            uncategorized = [t for t in schema if not any(t in tables for tables in merged_map.values())]
            if uncategorized and len(uncategorized) < 100:
                cat_summary = [f"{cat}: {', '.join(tables[:3])}" for cat, tables in merged_map.items() if tables]
                uncat_text = "\n".join([f"{t}: {', '.join([c['name'] for c in schema[t].get('columns', [])][:6])}" for t in uncategorized[:50]])

                prompt = f"""Already categorized:\n{chr(10).join(cat_summary)}

Categorize these remaining tables:
{uncat_text}

Respond with JSON: {{"table_map": {{"category": ["table1"]}}}}
Categories: customers, orders, products, users, employees, attendance, finance, payments, leads, contacts, settings, logs, reports, other
EXACT table names. JSON only."""

                raw = llm_chat_fn(prompt, temperature=0.1)
                parsed = self._parse_json(raw)
                if parsed:
                    for cat, tables in parsed.get("table_map", {}).items():
                        if cat not in merged_map:
                            merged_map[cat] = []
                        for t in tables:
                            if t in schema and t not in merged_map[cat]:
                                merged_map[cat].append(t)
        except Exception:
            pass

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
            "people_search_tables": self.people_search_tables,
            "relationships": self.relationships,
            "summary": self.summary,
            "learned_at": time.time(),
            "total_tables": len(schema),
        }
        self._save(brain_data)
        logger.info(f"  Brain built: {len(merged_info)} tables understood, {len(merged_map)} categories, {len(self.people_search_tables)} people tables")

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
                       "kitne", "kitna", "batao", "dikhao", "chahiye", "number", "naam", "name",
                       "full", "detail", "details", "more", "info", "information", "can", "you",
                       "sirf", "only", "just", "mobile", "email", "phone", "address"}
        words = set(q_lower.replace("'", "").replace("?", "").replace(".", "").replace(",", "").split())
        potential_names = words - stop_words
        # Remove very short words (likely not names)
        potential_names = {w for w in potential_names if len(w) > 2}

        if potential_names:
            # Probably searching for a person - ALWAYS check customer/user tables
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
                       "kitne", "batao", "dikhao", "chahiye", "number", "naam", "name", "full", "detail",
                       "details", "more", "info", "mobile", "email", "phone", "address", "can", "you",
                       "sirf", "only", "just", "give", "muze", "mujhe", "kya", "hai", "then", "check",
                       "in", "table", "user", "users", "customer", "customers", "order", "orders",
                       "data", "database", "connected", "search", "look", "looking", "for",
                       "from", "with", "this", "that", "these", "those", "also", "too",
                       "total", "much", "very", "really", "some", "any", "each", "every",
                       "new", "old", "first", "last", "next", "previous", "before", "after"}
        words = q_lower.replace("'", "").replace("?", "").replace(".", "").replace(",", "").split()
        names = [n for n in words if n not in stop_words and len(n) > 2]

        hints = []
        if names:
            name = names[0]
            hints.append(f"IMPORTANT: User is searching for a person/entity named '{name}'.")
            hints.append(f"Use ILIKE '%{name}%' on EVERY text/varchar column that could contain a name.")
            hints.append(f"Search multiple columns: WHERE col1 ILIKE '%{name}%' OR col2 ILIKE '%{name}%' OR col3 ILIKE '%{name}%'")
            hints.append(f"Use SELECT * to return all details.")
        return "\n".join(hints)

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
