import json
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import Engine, text

from agents.db_agent.db.inspector import DatabaseInspector
from agents.db_agent.tools.base import BaseTool
from shared.db import apply_session_search_path, ensure_session_replica, get_session_schema_or_public
from shared.observability import trace_span

logger = logging.getLogger(__name__)


class ModificationPlan(BaseModel):
    is_ambiguous: bool = Field(
        default=False,
        description="True ONLY if the request genuinely lacks necessary conditions, has ambiguous candidate targets, or requires user clarification before executing safely."
    )
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="Specific questions to ask user if is_ambiguous is True."
    )
    clarification_message: str = Field(
        default="",
        description="Natural language explanation of what is unclear and questions in the user's language."
    )
    action_type: Literal["insert", "update", "delete", "alter_table", "create_table", "drop_table", "unknown"] = Field(
        default="unknown",
        description="The classified CRUD or DDL action type."
    )
    target_table: str = Field(
        default="",
        description="Name of the table being modified or created."
    )
    sql_statement: str = Field(
        default="",
        description="Clean, valid PostgreSQL statement to execute the modification."
    )
    rollback_sql: Optional[str] = Field(
        default=None,
        description="SQL statement to reverse this modification if it can be statically determined."
    )
    description: str = Field(
        default="",
        description="Concise description of the change performed."
    )


class ModifyDatabaseTableTool(BaseTool):
    """
    CRUD tool for db_agent: executes INSERT, UPDATE, DELETE, ALTER TABLE, CREATE TABLE,
    and DROP TABLE operations on the active session's database replica.
    Validates ambiguities, asks clarifying questions if required, and records change history for undo.
    """

    name: str = "modify_database_table"
    description: str = (
        "Modifies database tables according to user requests (INSERT, UPDATE, DELETE rows, "
        "ALTER TABLE add/drop columns, CREATE TABLE, DROP TABLE) in the session database replica. "
        "Protects system tables (internal.*). Automatically detects ambiguities, asks clarifying questions if needed, "
        "and logs all changes with before/after state for full rollback (undo) support."
    )
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": "Natural language instruction of the requested modification (e.g. 'Add column discount NUMERIC(10,2)', 'Insert user Alice', 'Delete order 5').",
            },
            "table_name": {
                "type": "string",
                "description": "Optional explicit target table name if known.",
            },
            "action_type": {
                "type": "string",
                "enum": ["insert", "update", "delete", "alter_table", "create_table", "drop_table"],
                "description": "Optional operation classification.",
            },
            "session_id": {
                "type": "string",
                "description": "Active session ID to target the isolated session replica.",
            },
        },
        "required": ["instruction"],
    }

    def __init__(
        self,
        engine: Engine,
        inspector: Optional[DatabaseInspector] = None,
        chat_model: Optional[BaseChatModel] = None,
        llm: Optional[Any] = None,
    ) -> None:
        self.engine = engine
        self.inspector = inspector or DatabaseInspector(engine)
        if chat_model:
            self.chat_model = chat_model
        elif llm:
            self.chat_model = llm.get_chat_model() if hasattr(llm, "get_chat_model") else llm
        else:
            self.chat_model = None

    def execute(
        self,
        instruction: str,
        table_name: Optional[str] = None,
        action_type: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Executes the requested database modification with ambiguity detection,
        session schema isolation, and change history recording.
        """
        clean_instruction = instruction.strip()
        if not clean_instruction:
            return {"status": "error", "error": "Instruction cannot be empty."}

        # 1. Security guardrail: Protect internal.* system tables
        lowered = clean_instruction.lower()
        if "internal." in lowered or (table_name and table_name.lower().startswith("internal")):
            return {
                "status": "error",
                "error": "Security Restriction: Modifying internal system tables (internal.*) is strictly prohibited.",
            }

        # 2. Ensure session schema replica exists
        target_schema = ensure_session_replica(self.engine, session_id) if session_id else "public"

        # 3. Retrieve schema definitions for LLM context
        schema_summary = self.inspector.get_schema_summary(session_id=session_id, schema=target_schema)

        # 4. Use LLM to analyze intent, detect ambiguities, and formulate SQL
        plan = self._plan_modification(
            instruction=clean_instruction,
            schema_summary=schema_summary,
            table_name=table_name,
            action_type=action_type,
            target_schema=target_schema,
            session_id=session_id,
        )

        # 5. Handle clarification if genuinely ambiguous
        if plan.is_ambiguous:
            return {
                "status": "clarification_needed",
                "questions": plan.clarification_questions,
                "response": plan.clarification_message or "\n".join(plan.clarification_questions),
                "metadata": {
                    "status": "clarification_needed",
                    "questions": plan.clarification_questions,
                },
            }

        # 6. Validate planned table and SQL
        resolved_table = plan.target_table.strip().replace('"', '')
        if not resolved_table and table_name:
            resolved_table = table_name.strip().replace('"', '')

        if not plan.sql_statement:
            return {
                "status": "error",
                "error": "Could not generate valid SQL statement for this modification.",
            }

        # Security check on generated SQL
        if "internal." in plan.sql_statement.lower():
            return {
                "status": "error",
                "error": "Security Restriction: Modifying internal system tables is strictly prohibited.",
            }

        # 7. Pre-execution state capture & ambiguity verification for UPDATE/DELETE
        before_state: List[Dict[str, Any]] = []
        rollback_sql = plan.rollback_sql

        if plan.action_type in ("update", "delete") and resolved_table:
            before_state, ambiguity_error = self._capture_before_state(
                schema_name=target_schema,
                table_name=resolved_table,
                sql_statement=plan.sql_statement,
                action_type=plan.action_type,
            )
            if ambiguity_error:
                return ambiguity_error

            # Build precise rollback SQL from captured before_state if not already provided
            if not rollback_sql and before_state:
                rollback_sql = self._build_dml_rollback_sql(
                    schema_name=target_schema,
                    table_name=resolved_table,
                    action_type=plan.action_type,
                    before_state=before_state,
                )

        # 8. Execute SQL mutation within a transaction
        executed_sql = plan.sql_statement.strip()
        after_state: List[Dict[str, Any]] = []
        change_id: Optional[int] = None

        try:
            with self.engine.begin() as conn:
                apply_session_search_path(conn, session_id)

                # Execute modification
                result = conn.execute(text(executed_sql))
                rows_affected = result.rowcount if hasattr(result, "rowcount") else 0

                # For INSERT, if returned row exists
                if plan.action_type == "insert" and result.returns_rows:
                    try:
                        fetched = result.fetchall()
                        after_state = [dict(r._mapping) for r in fetched]
                        # Build rollback SQL to delete inserted IDs
                        if after_state and "id" in after_state[0]:
                            inserted_ids = [str(r["id"]) for r in after_state if "id" in r]
                            rollback_sql = f'DELETE FROM "{resolved_table}" WHERE id IN ({", ".join(inserted_ids)});'
                    except Exception:
                        pass

                # If CREATE TABLE, rollback is DROP TABLE
                if plan.action_type == "create_table" and resolved_table and not rollback_sql:
                    rollback_sql = f'DROP TABLE IF EXISTS "{resolved_table}" CASCADE;'

                # If ALTER TABLE ADD COLUMN, rollback is DROP COLUMN
                if plan.action_type == "alter_table" and not rollback_sql:
                    sql_lower = executed_sql.lower()
                    if "add column" in sql_lower:
                        idx = sql_lower.find("add column")
                        after = executed_sql[idx + len("add column"):].strip()
                        if after.lower().startswith("if not exists"):
                            after = after[len("if not exists"):].strip()
                        parts = after.split()
                        if parts:
                            new_col = parts[0].strip('"` \t\n\r,;')
                            rollback_sql = f'ALTER TABLE "{resolved_table}" DROP COLUMN IF EXISTS "{new_col}";'

                # 9. Record change in internal.change_history
                if session_id:
                    history_res = conn.execute(
                        text("""
                            INSERT INTO internal.change_history (
                                session_id, action_type, table_name, description,
                                executed_sql, rollback_sql, before_state, after_state
                            ) VALUES (
                                :session_id, :action_type, :table_name, :description,
                                :executed_sql, :rollback_sql, :before_state, :after_state
                            ) RETURNING id
                        """),
                        {
                            "session_id": session_id,
                            "action_type": plan.action_type.upper(),
                            "table_name": resolved_table,
                            "description": plan.description or f"{plan.action_type.upper()} on {resolved_table}",
                            "executed_sql": executed_sql,
                            "rollback_sql": rollback_sql or "-- Manual rollback required",
                            "before_state": json.dumps(before_state, default=str),
                            "after_state": json.dumps(after_state, default=str),
                        },
                    )
                    change_id = history_res.scalar()

        except Exception as exc:
            logger.error(f"Error executing database modification: {exc}", exc_info=True)
            return {
                "status": "error",
                "error": f"Database execution error: {exc}",
                "sql_attempted": executed_sql,
            }

        desc = plan.description or f"Successfully executed {plan.action_type.upper()} on '{resolved_table}'."
        return {
            "status": "success",
            "action": plan.action_type,
            "table_name": resolved_table,
            "change_id": change_id,
            "rows_affected": rows_affected,
            "sql_executed": executed_sql,
            "message": desc,
            "response": f"✅ {desc}\n\n```sql\n{executed_sql}\n```",
            "metadata": {
                "change_id": change_id,
                "table_name": resolved_table,
                "action": plan.action_type,
            },
        }

    def _plan_modification(
        self,
        instruction: str,
        schema_summary: str,
        table_name: Optional[str],
        action_type: Optional[str],
        target_schema: str,
        session_id: Optional[str],
    ) -> ModificationPlan:
        """
        Uses chat model to formulate the modification plan, classify action,
        and detect genuine ambiguities.
        """
        if not self.chat_model:
            # Fallback deterministic plan
            return ModificationPlan(
                is_ambiguous=False,
                action_type=action_type or "unknown",
                target_table=table_name or "",
                sql_statement=instruction,
                description=f"Direct SQL: {instruction}",
            )

        system_prompt = (
            "You are an expert PostgreSQL database administrator. "
            "Your task is to analyze user requests to modify database tables (INSERT, UPDATE, DELETE rows, "
            "ALTER TABLE, CREATE TABLE, DROP TABLE) and output an accurate, safe ModificationPlan.\n\n"
            "Core Guidelines:\n"
            "1. Ambiguity Detection:\n"
            "   - Set is_ambiguous = True only when essential targeting conditions are missing (e.g. user asks to 'update price' without specifying which product or what price, or 'delete' without clear targeting criteria).\n"
            "   - Avoid asking unnecessary questions when context allows reasonable inference (e.g. if the user says 'delete John' and there is only one users table, infer that the table is 'users').\n"
            "   - When is_ambiguous is True, provide a concise, polite explanation in 'clarification_message' and list the questions in 'clarification_questions', rather than executing an unverified guess.\n"
            "2. Table and Schema Rules:\n"
            "   - Avoid modifying or targeting 'internal.*' tables (chat_sessions, chat_messages, change_history).\n"
            "   - The user has full freedom to create any new tables they want (e.g. employees, logs, inventory).\n"
            "   - Generate clean PostgreSQL syntax without schema prefix, as search_path is configured.\n"
            "   - For INSERT statements, append 'RETURNING *' to capture generated values.\n"
            f"Active Database Schema ({target_schema}):\n{schema_summary}"
        )

        user_content = (
            f"User Instruction: {instruction}\n"
            f"Hint Table: {table_name or 'Auto-detect'}\n"
            f"Hint Action: {action_type or 'Auto-detect'}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        with trace_span(
            "db_agent.plan_table_modification",
            input_data={"instruction": instruction, "hint_table": table_name, "hint_action": action_type},
            metadata={"session_id": session_id, "target_schema": target_schema},
        ) as span:
            handler = span.get_langchain_handler()
            config = {"callbacks": [handler]} if handler else {}
            try:
                structured_model = self.chat_model.with_structured_output(ModificationPlan)
                result = structured_model.invoke(messages, config=config)
                if isinstance(result, dict):
                    result = ModificationPlan.model_validate(result)
                span.update(
                    output={
                        "is_ambiguous": result.is_ambiguous,
                        "action_type": result.action_type,
                        "target_table": result.target_table,
                        "sql_statement": result.sql_statement,
                    },
                    metadata={
                        "action_type": result.action_type,
                        "target_table": result.target_table,
                    },
                )
                return result
            except Exception as exc:
                logger.warning(f"Structured modification planning failed: {exc}, attempting raw fallback")
                fallback_plan = ModificationPlan(
                    is_ambiguous=False,
                    action_type="unknown",
                    target_table=table_name or "",
                    sql_statement=instruction,
                    description=instruction,
                )
                span.update(
                    output={"fallback": True, "sql_statement": instruction},
                    level="WARNING",
                )
                return fallback_plan

    def _capture_before_state(
        self,
        schema_name: str,
        table_name: str,
        sql_statement: str,
        action_type: str,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Extracts WHERE clause from UPDATE/DELETE statement, inspects target rows,
        and verifies if genuine ambiguity exists (e.g. multiple records for a singular intent).
        """
        sql_lower = sql_statement.lower()
        where_idx = -1
        pos = 0
        while True:
            idx = sql_lower.find("where", pos)
            if idx == -1:
                break
            before_char = sql_statement[idx - 1] if idx > 0 else " "
            after_char = sql_statement[idx + 5] if idx + 5 < len(sql_statement) else " "
            if before_char in (" ", "\t", "\n", "\r", ")") and after_char in (" ", "\t", "\n", "\r", "("):
                where_idx = idx
                break
            pos = idx + 5

        where_clause = sql_statement[where_idx + 5:].strip().rstrip(";") if where_idx != -1 else ""

        if not where_clause and action_type in ("update", "delete"):
            # Deleting or updating all rows without WHERE is dangerous unless explicitly requested
            return [], {
                "status": "clarification_needed",
                "questions": [
                    f"This operation will modify/delete ALL records in '{table_name}'. Are you sure you want to proceed without a WHERE condition?"
                ],
                "response": f"Warning: This query will modify or delete ALL records in table '{table_name}'. Please specify a WHERE condition or confirm this action for all rows.",
            }

        try:
            query = f'SELECT * FROM "{schema_name}"."{table_name}" WHERE {where_clause}'
            with self.engine.connect() as conn:
                rows = conn.execute(text(query)).fetchall()
                records = [dict(r._mapping) for r in rows]

                # Check for multiple candidates on singular delete intent
                if action_type == "delete" and len(records) > 1 and "limit" not in sql_statement.lower():
                    # Check if the query looked for a specific name/text in quotes
                    target_val = "specified criterion"
                    if "=" in where_clause:
                        after_eq = where_clause.split("=", 1)[1].strip()
                        if "'" in after_eq:
                            q1 = after_eq.find("'")
                            q2 = after_eq.find("'", q1 + 1)
                            if q2 != -1:
                                target_val = after_eq[q1 + 1:q2]
                    return [], {
                        "status": "clarification_needed",
                        "questions": [
                            f"Found {len(records)} records matching '{target_val}'. Please provide the specific ID or unique identifier to delete."
                        ],
                        "response": (
                            f"Found {len(records)} records matching '{target_val}' in table '{table_name}':\n"
                            + "\n".join(
                                f"- ID {r.get('id')}: {r.get('name', '')} ({r.get('email', '')})"
                                for r in records[:5]
                            )
                            + "\nPlease specify the exact ID of the record you want to delete."
                        ),
                    }

                return records, None
        except Exception as exc:
            logger.debug(f"Pre-check before state query failed or table not found: {exc}")
            return [], None

    def _build_dml_rollback_sql(
        self,
        schema_name: str,
        table_name: str,
        action_type: str,
        before_state: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Constructs reverse SQL statements to restore rows from before_state.
        """
        if not before_state:
            return None

        statements: List[str] = []
        if action_type == "delete":
            # Restore deleted rows via INSERT
            cols = list(before_state[0].keys())
            cols_str = ", ".join(f'"{c}"' for c in cols)
            for row in before_state:
                vals = []
                for c in cols:
                    v = row.get(c)
                    if v is None:
                        vals.append("NULL")
                    elif isinstance(v, (int, float)):
                        vals.append(str(v))
                    else:
                        escaped = str(v).replace("'", "''")
                        vals.append(f"'{escaped}'")
                vals_str = ", ".join(vals)
                statements.append(f'INSERT INTO "{schema_name}"."{table_name}" ({cols_str}) VALUES ({vals_str});')

        elif action_type == "update":
            # Restore previous values for updated rows
            for row in before_state:
                pk_val = row.get("id")
                if pk_val is None:
                    continue
                set_parts = []
                for k, v in row.items():
                    if k == "id":
                        continue
                    if v is None:
                        set_parts.append(f'"{k}" = NULL')
                    elif isinstance(v, (int, float)):
                        set_parts.append(f'"{k}" = {v}')
                    else:
                        escaped = str(v).replace("'", "''")
                        set_parts.append(f'"{k}" = \'{escaped}\'')
                if set_parts:
                    set_str = ", ".join(set_parts)
                    statements.append(f'UPDATE "{schema_name}"."{table_name}" SET {set_str} WHERE id = {pk_val};')

        return "\n".join(statements) if statements else None
