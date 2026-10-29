import json
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import Engine, text

from agents.db_agent.db.inspector import DatabaseInspector
from agents.db_agent.prompts import prompt_loader
from agents.db_agent.tools.base import BaseTool
from shared.db import apply_session_search_path, ensure_session_replica
from shared.observability import trace_span

logger = logging.getLogger(__name__)


def _format_sql_literal(value: Any) -> str:
    """Formats a Python value into a safe PostgreSQL literal representation."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


class ModificationPlan(BaseModel):
    """
    Structured output schema representing a planned database table or row modification.
    """

    is_ambiguous: bool = Field(
        default=False,
        description="True when the request lacks necessary targeting conditions, has ambiguous candidate targets, or requires user clarification before executing safely.",
    )
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="Specific questions to ask the user if is_ambiguous is True.",
    )
    clarification_message: str = Field(
        default="",
        description="Natural language explanation of what is unclear and questions in the user's language.",
    )
    action_type: Literal["insert", "update", "delete", "alter_table", "create_table", "drop_table", "unknown"] = Field(
        default="unknown",
        description="The classified CRUD or DDL action type.",
    )
    target_table: str = Field(
        default="",
        description="Name of the table being modified or created.",
    )
    sql_statement: str = Field(
        default="",
        description="Clean, valid PostgreSQL statement to execute the modification.",
    )
    rollback_sql: Optional[str] = Field(
        default=None,
        description="SQL statement to reverse this modification if it can be statically determined.",
    )
    description: str = Field(
        default="",
        description="Concise description of the change performed.",
    )


class ModifyDatabaseTableTool(BaseTool):
    """
    CRUD and DDL tool for db_agent: executes INSERT, UPDATE, DELETE, ALTER TABLE, CREATE TABLE,
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
        """
        Initializes the database table modification tool.

        Args:
            engine (Engine): SQLAlchemy database engine.
            inspector (Optional[DatabaseInspector]): Optional pre-configured schema inspector.
            chat_model (Optional[BaseChatModel]): Optional LangChain chat model instance.
            llm (Optional[Any]): Optional BaseLLM wrapper providing get_chat_model().
        """
        self.engine = engine
        self.inspector = inspector or DatabaseInspector(engine)
        if chat_model:
            self.chat_model = chat_model
        elif llm:
            self.chat_model = llm.get_chat_model() if hasattr(llm, "get_chat_model") else llm
        else:
            self.chat_model = None

    def _resolve_pk_column(
        self,
        schema_name: str,
        table_name: str,
        sample_row: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Resolves the primary key or best unique identifier column for a target table.

        Args:
            schema_name (str): Active PostgreSQL schema name.
            table_name (str): Target table name.
            sample_row (Optional[Dict[str, Any]]): Optional sample record dictionary to verify column presence.

        Returns:
            Optional[str]: Resolved primary key or identifier column name, or None.
        """
        pk_col = self.inspector.get_primary_key_column(table_name, schema=schema_name)
        if pk_col and (sample_row is None or pk_col in sample_row):
            return pk_col
        if sample_row:
            if "id" in sample_row:
                return "id"
            keys = list(sample_row.keys())
            if keys:
                return keys[0]
        return None

    def execute(
        self,
        instruction: str,
        table_name: Optional[str] = None,
        action_type: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_span: Optional[Any] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Executes the requested database modification with ambiguity detection,
        session schema isolation, and change history recording.

        Args:
            instruction (str): Natural language instruction or SQL modification request.
            table_name (Optional[str]): Optional target table hint.
            action_type (Optional[str]): Optional CRUD/DDL action classification hint.
            session_id (Optional[str]): Active session ID for session replica isolation.
            parent_span (Optional[Any]): Optional active observability span for nested tracing.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            Dict[str, Any]: Structured execution result or clarification prompt.
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
            parent_span=parent_span,
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

                result = conn.execute(text(executed_sql))
                rows_affected = result.rowcount if hasattr(result, "rowcount") else 0

                # For INSERT, capture returned rows and build dynamic rollback statement
                if plan.action_type == "insert" and result.returns_rows:
                    try:
                        fetched = result.fetchall()
                        after_state = [dict(r._mapping) for r in fetched]
                        if after_state:
                            pk_col = self._resolve_pk_column(target_schema, resolved_table, after_state[0])
                            if pk_col and pk_col in after_state[0]:
                                formatted_ids = [
                                    _format_sql_literal(r[pk_col])
                                    for r in after_state
                                    if r.get(pk_col) is not None
                                ]
                                if formatted_ids:
                                    rollback_sql = (
                                        f'DELETE FROM "{resolved_table}" '
                                        f'WHERE "{pk_col}" IN ({", ".join(formatted_ids)});'
                                    )
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
        parent_span: Optional[Any] = None,
    ) -> ModificationPlan:
        """
        Uses the configured chat model to formulate the modification plan, classify the action,
        and detect genuine ambiguities.

        Args:
            instruction (str): Natural language modification request.
            schema_summary (str): Formatted database schema summary.
            table_name (Optional[str]): Optional target table hint.
            action_type (Optional[str]): Optional action classification hint.
            target_schema (str): Active PostgreSQL schema name.
            session_id (Optional[str]): Active session ID.
            parent_span (Optional[Any]): Optional parent observability span.

        Returns:
            ModificationPlan: Structured modification plan.
        """
        if not self.chat_model:
            return ModificationPlan(
                is_ambiguous=False,
                action_type=action_type or "unknown",
                target_table=table_name or "",
                sql_statement=instruction,
                description=f"Direct SQL: {instruction}",
            )

        system_prompt = prompt_loader.render(
            "modify_table",
            target_schema=target_schema,
            schema_summary=schema_summary,
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
            parent=parent_span,
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
        Extracts the WHERE clause from an UPDATE or DELETE statement, inspects target rows,
        and verifies if genuine ambiguity exists (e.g. multiple records matching a singular delete intent).

        Args:
            schema_name (str): Active PostgreSQL schema name.
            table_name (str): Target table name.
            sql_statement (str): Planned UPDATE or DELETE SQL statement.
            action_type (str): Classified action type ('update' or 'delete').

        Returns:
            Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]: Tuple of (captured before-state records, optional clarification error dict).
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
            return [], {
                "status": "clarification_needed",
                "questions": [
                    f"This operation will modify or delete every record in '{table_name}'. Are you sure you want to proceed without a WHERE condition?"
                ],
                "response": (
                    f"Warning: This query will modify or delete every record in table '{table_name}'. "
                    "Please specify a WHERE condition or explicitly confirm this action for the entire table."
                ),
            }

        try:
            query = f'SELECT * FROM "{schema_name}"."{table_name}" WHERE {where_clause}'
            with self.engine.connect() as conn:
                rows = conn.execute(text(query)).fetchall()
                records = [dict(r._mapping) for r in rows]

                # Check for multiple candidates on singular delete intent
                if action_type == "delete" and len(records) > 1 and "limit" not in sql_statement.lower():
                    target_val = "specified criterion"
                    if "=" in where_clause:
                        after_eq = where_clause.split("=", 1)[1].strip()
                        if "'" in after_eq:
                            q1 = after_eq.find("'")
                            q2 = after_eq.find("'", q1 + 1)
                            if q2 != -1:
                                target_val = after_eq[q1 + 1:q2]

                    sample_lines: List[str] = []
                    for rec in records[:5]:
                        preview_pairs = [f"{k}={v}" for k, v in list(rec.items())[:3] if v is not None]
                        sample_lines.append(f"- {', '.join(preview_pairs)}")

                    return [], {
                        "status": "clarification_needed",
                        "questions": [
                            f"Found {len(records)} records matching '{target_val}'. Please provide the specific identifier to delete."
                        ],
                        "response": (
                            f"Found {len(records)} records matching '{target_val}' in table '{table_name}':\n"
                            + "\n".join(sample_lines)
                            + "\nPlease specify the exact identifier of the record you want to delete."
                        ),
                    }

                return records, None
        except Exception as exc:
            logger.debug(f"Pre-check before-state query failed or table not found: {exc}")
            return [], None

    def _build_dml_rollback_sql(
        self,
        schema_name: str,
        table_name: str,
        action_type: str,
        before_state: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Constructs reverse SQL statements to restore rows from captured before_state.

        Args:
            schema_name (str): Active PostgreSQL schema name.
            table_name (str): Target table name.
            action_type (str): DML operation type ('delete' or 'update').
            before_state (List[Dict[str, Any]]): List of row dictionaries captured prior to execution.

        Returns:
            Optional[str]: Semicolon-delimited SQL statements to undo the DML change, or None.
        """
        if not before_state:
            return None

        statements: List[str] = []
        if action_type == "delete":
            cols = list(before_state[0].keys())
            cols_str = ", ".join(f'"{c}"' for c in cols)
            for row in before_state:
                vals_str = ", ".join(_format_sql_literal(row.get(c)) for c in cols)
                statements.append(f'INSERT INTO "{schema_name}"."{table_name}" ({cols_str}) VALUES ({vals_str});')

        elif action_type == "update":
            pk_col = self._resolve_pk_column(schema_name, table_name, before_state[0])
            if not pk_col:
                return None

            for row in before_state:
                pk_val = row.get(pk_col)
                if pk_val is None:
                    continue
                set_parts = [
                    f'"{k}" = {_format_sql_literal(v)}'
                    for k, v in row.items()
                    if k != pk_col
                ]
                if set_parts:
                    set_str = ", ".join(set_parts)
                    pk_literal = _format_sql_literal(pk_val)
                    statements.append(
                        f'UPDATE "{schema_name}"."{table_name}" SET {set_str} WHERE "{pk_col}" = {pk_literal};'
                    )

        return "\n".join(statements) if statements else None
