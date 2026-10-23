import logging
from typing import Any, Dict, Optional
from sqlalchemy import Engine, text

from agents.db_agent.tools.base import BaseTool
from shared.db import apply_session_search_path, ensure_session_replica

logger = logging.getLogger(__name__)


class RollbackDatabaseChangeTool(BaseTool):
    """
    Tool that reverts previous database changes in the active session
    by executing recorded rollback SQL from internal.change_history.
    """

    name: str = "rollback_database_change"
    description: str = (
        "Reverts and rolls back previous database modifications (INSERT, UPDATE, DELETE, ALTER TABLE, CREATE TABLE) "
        "in the current session using the recorded change history (e.g. for user requests like 'undo', 'revert changes', "
        "'rollback', 'undo previous action')."
    )
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Target session ID whose database change should be reverted.",
            },
            "change_id": {
                "type": "integer",
                "description": "Optional specific change history ID to revert. If omitted, the latest un-reverted change is rolled back.",
            },
        },
    }

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def execute(
        self,
        session_id: Optional[str] = None,
        change_id: Optional[int] = None,
        target_change_id: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Rolls back the latest or specified un-reverted change in the session replica.
        """
        effective_cid = target_change_id if target_change_id is not None else change_id
        if not session_id:
            return {
                "status": "error",
                "error": "Session ID is required to locate session change history.",
            }

        target_schema = ensure_session_replica(self.engine, session_id)

        # 1. Fetch target un-reverted change record
        with self.engine.begin() as conn:
            if effective_cid:
                row = conn.execute(
                    text("""
                        SELECT id, action_type, table_name, description, executed_sql, rollback_sql
                        FROM internal.change_history
                        WHERE id = :cid AND session_id = :sid AND is_reverted = FALSE
                    """),
                    {"cid": effective_cid, "sid": session_id},
                ).fetchone()
            else:
                row = conn.execute(
                    text("""
                        SELECT id, action_type, table_name, description, executed_sql, rollback_sql
                        FROM internal.change_history
                        WHERE session_id = :sid AND is_reverted = FALSE
                        ORDER BY id DESC LIMIT 1
                    """),
                    {"sid": session_id},
                ).fetchone()

            if not row:
                return {
                    "status": "warning",
                    "response": "There are no previous database changes to roll back in this session (or all recent changes have already been reverted).",
                    "message": "No active changes found to roll back in this session.",
                }

            rec_id, action_type, table_name, description, executed_sql, rollback_sql = (
                row[0], row[1], row[2], row[3], row[4], row[5]
            )

            if not rollback_sql or rollback_sql.strip().startswith("--"):
                return {
                    "status": "error",
                    "error": f"Cannot automatically roll back change #{rec_id} ({description}): no automated rollback SQL is available.",
                }

            # 2. Execute rollback statement on session schema
            try:
                apply_session_search_path(conn, session_id)
                # Split multiple statements if any
                for stmt in [s.strip() for s in rollback_sql.split(";") if s.strip()]:
                    conn.execute(text(stmt))

                # 3. Mark change record as reverted
                conn.execute(
                    text("UPDATE internal.change_history SET is_reverted = TRUE WHERE id = :id"),
                    {"id": rec_id},
                )
            except Exception as exc:
                logger.error(f"Error executing rollback SQL for change #{rec_id}: {exc}", exc_info=True)
                return {
                    "status": "error",
                    "error": f"Failed to execute rollback for change #{rec_id}: {exc}",
                    "rollback_sql": rollback_sql,
                }

        msg = f"Successfully reverted action: {description} (table '{table_name}')."
        return {
            "status": "success",
            "reverted_change_id": rec_id,
            "reverted_action": action_type,
            "table_name": table_name,
            "message": msg,
            "response": f"↩️ {msg}\n\n```sql\n{rollback_sql}\n```",
            "metadata": {
                "reverted_change_id": rec_id,
                "table_name": table_name,
                "action": "rollback",
            },
        }
