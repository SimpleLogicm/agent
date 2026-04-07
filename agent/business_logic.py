import json
import os
from typing import List, Dict, Any, Optional
import ollama as ollama_client
from config import settings


COMMON_WORKFLOWS = {
    "healthcare": [
        {"name": "book_appointment", "steps": ["check_doctor_availability", "select_time_slot", "create_appointment", "confirm_booking"], "tables": ["doctors", "appointments", "patients"]},
        {"name": "cancel_appointment", "steps": ["find_appointment", "update_status_cancelled", "notify_doctor"], "tables": ["appointments"]},
        {"name": "patient_registration", "steps": ["collect_info", "check_duplicate", "create_patient_record"], "tables": ["patients"]},
        {"name": "view_medical_history", "steps": ["find_patient", "get_records", "format_timeline"], "tables": ["patients", "medical_records", "prescriptions"]},
    ],
    "e-commerce": [
        {"name": "place_order", "steps": ["validate_cart", "check_inventory", "calculate_total", "create_order", "process_payment"], "tables": ["products", "orders", "order_items", "payments"]},
        {"name": "track_order", "steps": ["find_order", "get_shipping_status"], "tables": ["orders", "shipments"]},
        {"name": "return_item", "steps": ["find_order_item", "create_return_request", "process_refund"], "tables": ["orders", "returns", "payments"]},
    ],
    "education": [
        {"name": "enroll_student", "steps": ["check_prerequisites", "verify_capacity", "create_enrollment"], "tables": ["students", "courses", "enrollments"]},
        {"name": "record_grade", "steps": ["find_enrollment", "update_grade", "calculate_gpa"], "tables": ["enrollments", "grades"]},
        {"name": "view_transcript", "steps": ["find_student", "get_all_grades", "format_transcript"], "tables": ["students", "enrollments", "grades"]},
    ],
    "finance": [
        {"name": "create_transaction", "steps": ["validate_account", "check_balance", "execute_transfer", "record_transaction"], "tables": ["accounts", "transactions"]},
        {"name": "generate_statement", "steps": ["find_account", "get_transactions_in_period", "calculate_balance"], "tables": ["accounts", "transactions"]},
    ],
    "hr": [
        {"name": "apply_leave", "steps": ["check_leave_balance", "check_conflicts", "create_leave_request"], "tables": ["employees", "leaves"]},
        {"name": "process_payroll", "steps": ["get_employees", "calculate_salary", "apply_deductions", "generate_payslip"], "tables": ["employees", "salary", "payroll"]},
    ],
    "restaurant": [
        {"name": "make_reservation", "steps": ["check_availability", "select_table", "create_reservation"], "tables": ["tables", "reservations"]},
        {"name": "place_food_order", "steps": ["select_items", "calculate_total", "create_order"], "tables": ["menu", "orders"]},
    ],
}

KNOWLEDGE_FILE = "agent_knowledge.json"


class BusinessLogicLearner:
    def __init__(self):
        self.workflows: List[Dict[str, Any]] = []
        self.entity_map: Dict[str, str] = {}
        self.domain: str = "general"
        self.knowledge_path: str = ""

    def learn(self, domain: str, schema: Dict[str, Any],
              codebase_info: Optional[Dict] = None,
              project_path: str = ".") -> Dict[str, Any]:
        self.domain = domain
        self.knowledge_path = os.path.join(project_path, KNOWLEDGE_FILE)

        self.entity_map = self._map_entities(schema)
        self.workflows = self._detect_workflows(domain, schema)

        if codebase_info:
            code_workflows = self._learn_from_code(codebase_info)
            self.workflows.extend(code_workflows)

        llm_workflows = self._learn_from_llm(schema)
        if llm_workflows:
            self.workflows.extend(llm_workflows)

        self._deduplicate_workflows()
        self._save_knowledge()

        return {
            "domain": self.domain,
            "entity_map": self.entity_map,
            "workflows_learned": len(self.workflows),
            "workflows": [{"name": w["name"], "steps": w["steps"]} for w in self.workflows],
        }

    def _map_entities(self, schema: Dict[str, Any]) -> Dict[str, str]:
        entity_map = {}
        for table_name, table_info in schema.items():
            clean_name = table_name.replace("_", " ").replace("-", " ").title()
            entity_map[table_name] = clean_name

            columns = table_info.get("columns", [])
            col_names = [c["name"] for c in columns]
            if any(n in col_names for n in ["name", "title", "label"]):
                entity_map[f"{table_name}_display"] = next(
                    n for n in ["name", "title", "label"] if n in col_names
                )
        return entity_map

    def _detect_workflows(self, domain: str, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        workflows = []
        table_names = set(t.lower() for t in schema.keys())

        if domain in COMMON_WORKFLOWS:
            for wf in COMMON_WORKFLOWS[domain]:
                required_tables = set(t.lower() for t in wf["tables"])
                overlap = required_tables & table_names
                if len(overlap) >= len(required_tables) * 0.5:
                    workflows.append({
                        "name": wf["name"],
                        "steps": wf["steps"],
                        "tables": list(overlap),
                        "source": "pattern_match",
                    })
        return workflows

    def _learn_from_code(self, codebase_info: Dict) -> List[Dict[str, Any]]:
        workflows = []
        routes = codebase_info.get("routes", [])

        action_groups: Dict[str, List[str]] = {}
        for route in routes:
            path = route.get("path", "")
            method = route.get("method", "GET")
            parts = [p for p in path.split("/") if p and not p.startswith("{") and not p.startswith(":")]
            if parts:
                resource = parts[-1] if len(parts) == 1 else parts[-2] if parts[-1] in ("create", "update", "delete", "list") else parts[-1]
                if resource not in action_groups:
                    action_groups[resource] = []
                action_groups[resource].append(f"{method} {path}")

        for resource, actions in action_groups.items():
            if len(actions) >= 2:
                workflows.append({
                    "name": f"manage_{resource}",
                    "steps": actions[:5],
                    "tables": [resource],
                    "source": "code_analysis",
                })
        return workflows

    def _learn_from_llm(self, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        schema_text = ""
        for table, info in list(schema.items())[:10]:
            cols = [c["name"] for c in info.get("columns", [])]
            schema_text += f"Table '{table}': columns = {cols}\n"

        prompt = f"""Given this database schema, suggest 3-5 business workflows that this system likely supports.

Schema:
{schema_text}

Respond ONLY with valid JSON array (no markdown):
[
  {{"name": "workflow_name", "steps": ["step1", "step2"], "tables": ["table1"]}},
]"""

        try:
            response = ollama_client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2},
            )
            text = response["message"]["content"].strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end > start:
                workflows = json.loads(text[start:end])
                for w in workflows:
                    w["source"] = "llm_learned"
                return workflows
        except Exception:
            pass
        return []

    def _deduplicate_workflows(self):
        seen = set()
        unique = []
        for w in self.workflows:
            if w["name"] not in seen:
                seen.add(w["name"])
                unique.append(w)
        self.workflows = unique

    def _save_knowledge(self):
        knowledge = {
            "domain": self.domain,
            "entity_map": self.entity_map,
            "workflows": self.workflows,
        }
        try:
            with open(self.knowledge_path, "w") as f:
                json.dump(knowledge, f, indent=2)
        except Exception:
            pass

    def load_knowledge(self, project_path: str = ".") -> bool:
        path = os.path.join(project_path, KNOWLEDGE_FILE)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                self.domain = data.get("domain", "general")
                self.entity_map = data.get("entity_map", {})
                self.workflows = data.get("workflows", [])
                return True
            except Exception:
                pass
        return False

    def get_workflow_context(self) -> str:
        if not self.workflows:
            return "No business workflows detected yet."

        lines = [f"Domain: {self.domain}", f"Known Workflows ({len(self.workflows)}):"]
        for w in self.workflows:
            lines.append(f"  - {w['name']}: {' -> '.join(w['steps'])}")
        return "\n".join(lines)
