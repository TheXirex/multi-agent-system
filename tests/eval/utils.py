import datetime
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import requests
import yaml

logger = logging.getLogger("eval_utils")
logger.addHandler(logging.NullHandler())

DEFAULT_SPEC_PATH = Path(__file__).parent / "scenarios.yaml"


def load_scenarios(spec_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Loads scenario definitions from the YAML specification file."""
    target_path = spec_path or DEFAULT_SPEC_PATH
    with open(target_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("scenarios", [])


class EvaluationRunner:
    """Provides client utilities for executing turns, uploading fixtures, scoring assertions, and recording Langfuse telemetry."""

    def __init__(
        self,
        backend_url: str = "http://localhost:8000",
        langfuse_host: str = "http://localhost:3000",
        public_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ) -> None:
        """Initializes endpoints and authentication credentials for backend and Langfuse."""
        self.backend_url = backend_url.rstrip("/")
        self.langfuse_host = langfuse_host.rstrip("/")
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-multi-agent-system")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-multi-agent-system")
        self.auth = (self.public_key, self.secret_key)

    def sync_langfuse_dataset(self, dataset_name: str, description: str, scenarios: List[Dict[str, Any]]) -> None:
        """Registers or refreshes dataset items for each scenario turn in Langfuse."""
        headers = {"Content-Type": "application/json"}
        try:
            requests.post(
                f"{self.langfuse_host}/api/public/datasets",
                auth=self.auth,
                headers=headers,
                json={"name": dataset_name, "description": description},
                timeout=10,
            )
            for scen in scenarios:
                scen_id = scen["id"]
                for turn in scen.get("turns", []):
                    turn_id = turn["turn_id"]
                    item_id = f"{scen_id}_t{turn_id:02d}"
                    user_query = turn.get("user_query") or f"Upload file: {turn.get('file_path')}"
                    item_payload = {
                        "datasetName": dataset_name,
                        "id": item_id,
                        "status": "ACTIVE",
                        "input": {
                            "scenario_id": scen_id,
                            "turn_id": turn_id,
                            "user_query": user_query,
                            "action": turn.get("action", "query"),
                        },
                        "expectedOutput": {
                            "expected_route": turn.get("expected_route", "tools" if turn.get("action") != "upload" else "upload"),
                            "expected_tools": turn.get("expected_tools", ["ingest_tabular_file"] if turn.get("action") == "upload" else []),
                            "expected_metadata_keys": turn.get("expected_metadata_keys", []),
                            "assertions": turn.get("assertions", []),
                        },
                        "metadata": {
                            "scenario_id": scen_id,
                            "turn_id": turn_id,
                            "scenario_description": scen.get("description", ""),
                        },
                    }
                    requests.post(
                        f"{self.langfuse_host}/api/public/dataset-items",
                        auth=self.auth,
                        headers=headers,
                        json=item_payload,
                        timeout=10,
                    )
        except Exception as exc:
            logger.debug(f"Failed to sync dataset with Langfuse: {exc}")

    def create_session(self, title: str) -> str:
        """Provisions a persistent session in the backend database and returns its unique ID."""
        url = f"{self.backend_url}/api/sessions"
        response = requests.post(url, json={"title": title}, timeout=20)
        response.raise_for_status()
        data = response.json()
        return str(data["id"])

    def execute_turn(self, session_id: str, query: str) -> Dict[str, Any]:
        """Streams a conversational turn from the backend and returns aggregated response and metadata."""
        url = f"{self.backend_url}/api/query/stream"
        payload = {"query": query, "session_id": session_id}
        start_ts = time.time()
        response = requests.post(url, json=payload, stream=True, timeout=240)
        response.raise_for_status()

        tools_called: List[str] = []
        statuses: List[str] = []
        final_response = ""
        metadata: Dict[str, Any] = {}
        trace_id: Optional[str] = None

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue

            event = json.loads(decoded[6:])
            event_type = event.get("type")

            if event_type == "status":
                status_val = event.get("status")
                if status_val:
                    statuses.append(status_val)
                tool_name = event.get("tool_name")
                if tool_name and tool_name not in tools_called:
                    tools_called.append(tool_name)

            elif event_type == "result":
                final_response = event.get("response", "")
                metadata = event.get("metadata", {})
                trace_id = event.get("trace_id") or metadata.get("trace_id")

        duration_s = round(time.time() - start_ts, 2)
        return {
            "response": final_response,
            "metadata": metadata,
            "tools_called": tools_called,
            "statuses": statuses,
            "trace_id": trace_id,
            "duration_s": duration_s,
        }

    def execute_upload(self, session_id: str, file_path_str: str) -> Dict[str, Any]:
        """Uploads a fixture file to the backend via POST /api/upload and returns execution results."""
        file_path = Path(file_path_str)
        if not file_path.exists():
            return {
                "action": "upload",
                "status": "error",
                "error": f"Fixture file '{file_path_str}' does not exist on disk.",
                "table_names": [],
                "response": f"File not found: {file_path_str}",
                "metadata": {},
                "tools_called": [],
                "duration_s": 0.0,
                "trace_id": None,
            }

        url = f"{self.backend_url}/api/upload"
        filename = file_path.name
        content = file_path.read_bytes()
        start_ts = time.time()

        if filename.endswith(".csv"):
            content_type = "text/csv"
        elif filename.endswith(".xlsx"):
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif filename.endswith(".xls"):
            content_type = "application/vnd.ms-excel"
        else:
            content_type = "text/plain"

        files = {"file": (filename, content, content_type)}
        data = {"session_id": session_id}

        try:
            response = requests.post(url, files=files, data=data, timeout=60)
            duration_s = round(time.time() - start_ts, 2)
            if response.status_code == 200:
                res_json = response.json()
                table_names = res_json.get("table_names", [])
                msg = res_json.get("message", "")
                return {
                    "action": "upload",
                    "status_code": 200,
                    "status": res_json.get("status", "success"),
                    "table_names": table_names,
                    "message": msg,
                    "response": msg,
                    "metadata": {"table_names": table_names},
                    "tools_called": ["ingest_tabular_file"],
                    "duration_s": duration_s,
                    "trace_id": None,
                }
            else:
                try:
                    err_detail = response.json().get("detail", response.text)
                except Exception:
                    err_detail = response.text
                return {
                    "action": "upload",
                    "status_code": response.status_code,
                    "status": "error",
                    "error": str(err_detail),
                    "response": str(err_detail),
                    "metadata": {"error": str(err_detail)},
                    "tools_called": [],
                    "duration_s": duration_s,
                    "trace_id": None,
                }
        except Exception as exc:
            duration_s = round(time.time() - start_ts, 2)
            return {
                "action": "upload",
                "status": "error",
                "error": str(exc),
                "response": str(exc),
                "metadata": {"error": str(exc)},
                "tools_called": [],
                "duration_s": duration_s,
                "trace_id": None,
            }

    def evaluate_turn(
        self,
        turn_spec: Dict[str, Any],
        actual_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluates actual turn execution against expected routing, tools, metadata, and assertions."""
        if turn_spec.get("action") == "upload":
            expected_status = turn_spec.get("expected_status", "success")
            actual_status = actual_result.get("status")
            status_pass = (actual_status == expected_status)
            routing_score = 1.0 if status_pass else 0.0
            tool_score = 1.0
            metadata_score = 1.0

            assertion_failures: List[str] = []
            for rule in turn_spec.get("assertions", []):
                rule_type = rule.get("type")
                if rule_type == "upload_success":
                    if actual_status != "success":
                        assertion_failures.append(f"Upload failed: {actual_result.get('error')}")
                    expected_tbl = rule.get("table")
                    if expected_tbl and expected_tbl not in actual_result.get("table_names", []):
                        assertion_failures.append(f"Expected table '{expected_tbl}' missing from created tables")
                elif rule_type == "upload_error_contains":
                    expected_snippet = str(rule.get("text", "")).lower()
                    actual_err = str(actual_result.get("error", "")).lower()
                    if expected_snippet not in actual_err:
                        assertion_failures.append(f"Expected error containing '{expected_snippet}', got: '{actual_err}'")

            total_assertions = len(turn_spec.get("assertions", []))
            assertions_score = 1.0 if not assertion_failures else 0.0
            passed = status_pass and len(assertion_failures) == 0
            return {
                "routing_score": routing_score,
                "tool_score": tool_score,
                "metadata_score": metadata_score,
                "assertions_score": assertions_score,
                "assertions_pass": len(assertion_failures) == 0,
                "assertion_failures": assertion_failures,
                "passed": passed,
            }

        expected_route = turn_spec.get("expected_route", "tools")
        expected_tools = turn_spec.get("expected_tools", [])
        expected_keys = turn_spec.get("expected_metadata_keys", [])
        assertions = turn_spec.get("assertions", [])

        tools_called = actual_result.get("tools_called", [])
        metadata = actual_result.get("metadata", {})
        response_text = actual_result.get("response", "")
        statuses = actual_result.get("statuses", [])

        # 1. Routing score
        routing_pass = True
        if expected_route == "direct":
            routing_pass = len(tools_called) == 0 and ("direct" in statuses or not metadata.get("guardrail_triggered"))
        elif expected_route == "refusal":
            routing_pass = len(tools_called) == 0 and (
                bool(metadata.get("guardrail_triggered")) or "refusal" in statuses
            )
        elif expected_route == "clarification":
            routing_pass = (
                metadata.get("status") == "clarification_needed"
                or bool(metadata.get("questions"))
                or "?" in response_text
            )
        elif expected_route == "tools":
            routing_pass = len(tools_called) > 0

        routing_score = 1.0 if routing_pass else 0.0

        # 2. Tool score
        if not expected_tools:
            tool_score = 1.0 if len(tools_called) == 0 else 0.0
        else:
            matched_required = [t for t in expected_tools if t in tools_called]
            tool_score = round(len(matched_required) / len(expected_tools), 2)

        # 3. Metadata score
        if not expected_keys:
            metadata_score = 1.0
        else:
            present_keys = [k for k in expected_keys if metadata.get(k) is not None]
            metadata_score = round(len(present_keys) / len(expected_keys), 2)

        # 4. Assertions evaluation
        assertion_failures = []
        resp_lower = response_text.lower()
        sql_query = str(metadata.get("sql_query") or "")
        sql_upper = sql_query.upper()

        for rule in assertions:
            rule_type = rule.get("type")
            if rule_type == "not_empty":
                if not response_text.strip():
                    assertion_failures.append("Response is empty")

            elif rule_type == "no_sql":
                if "```sql" in resp_lower or "select " in resp_lower:
                    assertion_failures.append("SQL code leaked into direct conversational response")

            elif rule_type == "contains_tables":
                schema_tables = [str(t).lower() for t in (metadata.get("schema_tables") or [])]
                for tbl in rule.get("tables", []):
                    tbl_low = str(tbl).lower()
                    if tbl_low not in resp_lower and tbl_low not in schema_tables:
                        assertion_failures.append(f"Expected table '{tbl}' missing from schema overview")

            elif rule_type == "forbidden_phrases":
                for phrase in rule.get("phrases", []):
                    if str(phrase).lower() in resp_lower:
                        assertion_failures.append(f"Forbidden phrase found in response: '{phrase}'")

            elif rule_type == "refusal_polite":
                if not response_text.strip() or not metadata.get("guardrail_triggered"):
                    assertion_failures.append("Expected polite guardrail refusal was not triggered")

            elif rule_type == "sql_syntax_valid":
                if "SELECT" not in sql_upper or "FROM" not in sql_upper:
                    assertion_failures.append("Valid SELECT ... FROM statement missing in sql_query")

            elif rule_type == "target_table":
                expected_tbl = str(rule.get("name", "")).lower()
                actual_tbls = [str(t).lower() for t in (metadata.get("table_names") or [])]
                if metadata.get("table_name"):
                    actual_tbls.append(str(metadata["table_name"]).lower())
                if expected_tbl not in actual_tbls and expected_tbl not in sql_query.lower():
                    assertion_failures.append(f"Target table '{expected_tbl}' not referenced")

            elif rule_type == "sql_contains_join":
                if "JOIN" not in sql_upper:
                    assertion_failures.append("Expected JOIN clause missing in sql_query")

            elif rule_type == "chart_generated":
                if not (metadata.get("chart_id") or metadata.get("chart_ids")):
                    assertion_failures.append("Expected interactive chart_id missing from metadata")

            elif rule_type == "ml_metrics_present":
                metrics = rule.get("metrics", [])
                if metrics and not any(str(m).lower() in resp_lower for m in metrics):
                    assertion_failures.append(f"Expected ML metrics {metrics} missing from response")

            elif rule_type == "mutation_recorded":
                if not metadata.get("change_id"):
                    assertion_failures.append("Expected change_id missing after database mutation")

            elif rule_type == "record_found":
                expected_text = str(rule.get("text", "")).lower()
                if expected_text and expected_text not in resp_lower:
                    assertion_failures.append(f"Expected record '{expected_text}' not found in response")

            elif rule_type == "clarification_requested":
                if metadata.get("status") != "clarification_needed" and not metadata.get("questions"):
                    assertion_failures.append("Clarification status/questions not returned for ambiguous mutation")

            elif rule_type == "rollback_successful":
                if not metadata.get("reverted_change_id"):
                    assertion_failures.append("Expected reverted_change_id missing after rollback")

        total_assertions = len(assertions)
        if total_assertions == 0:
            assertions_score = 1.0
        else:
            passed_assertions = max(0, total_assertions - len(assertion_failures))
            assertions_score = round(passed_assertions / total_assertions, 2)

        final_verdict = (
            routing_score >= 1.0
            and tool_score >= 1.0
            and metadata_score >= 0.8
            and len(assertion_failures) == 0
        )

        return {
            "routing_score": routing_score,
            "tool_score": tool_score,
            "metadata_score": metadata_score,
            "assertions_score": assertions_score,
            "assertions_pass": len(assertion_failures) == 0,
            "assertion_failures": assertion_failures,
            "passed": final_verdict,
        }

    def record_langfuse_telemetry(
        self,
        trace_id: Optional[str],
        eval_scores: Dict[str, Any],
        scenario_id: str,
        turn_id: int,
        run_name: str,
        session_id: str,
    ) -> None:
        """Links trace to Langfuse dataset run item and posts individual evaluation scores."""
        if not trace_id:
            return

        headers = {"Content-Type": "application/json"}
        item_id = f"{scenario_id}_t{turn_id:02d}"

        run_item_payload = {
            "runName": run_name,
            "runDescription": f"Eval ({run_name})",
            "datasetItemId": item_id,
            "traceId": trace_id,
            "metadata": {
                "session_id": session_id,
                "scenario_id": scenario_id,
                "turn_id": turn_id,
                "passed": eval_scores["passed"],
            },
        }
        try:
            requests.post(
                f"{self.langfuse_host}/api/public/dataset-run-items",
                auth=self.auth,
                headers=headers,
                json=run_item_payload,
                timeout=10,
            )
        except Exception as exc:
            logger.debug(f"Unable to link dataset run item in Langfuse: {exc}")

        scores = [
            {"name": "routing_accuracy", "value": eval_scores["routing_score"]},
            {"name": "tool_selection_score", "value": eval_scores["tool_score"]},
            {"name": "metadata_completeness", "value": eval_scores["metadata_score"]},
            {"name": "assertions_score", "value": eval_scores["assertions_score"]},
            {"name": "eval_verdict", "value": 1.0 if eval_scores["passed"] else 0.0},
        ]

        comment_text = f"[{run_name}] {scenario_id} t{turn_id}"
        if eval_scores["assertion_failures"]:
            comment_text += f" | Failures: {', '.join(eval_scores['assertion_failures'])}"

        for sc in scores:
            score_payload = {
                "traceId": trace_id,
                "name": sc["name"],
                "value": sc["value"],
                "comment": comment_text,
            }
            try:
                requests.post(
                    f"{self.langfuse_host}/api/public/scores",
                    auth=self.auth,
                    headers=headers,
                    json=score_payload,
                    timeout=10,
                )
            except Exception as exc:
                logger.debug(f"Unable to post score to Langfuse: {exc}")

