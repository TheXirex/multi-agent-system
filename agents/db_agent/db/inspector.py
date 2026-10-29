from typing import Any, List, Optional
from sqlalchemy import Engine, inspect
from shared.db import ensure_session_replica


class DatabaseInspector:
    """
    Inspects database tables, columns, and relationships to provide schema context.
    Supports isolated session replica schemas when a session_id is provided.
    """

    def __init__(self, engine: Engine, schema: str = "public") -> None:
        """Initializes the database inspector with a SQLAlchemy engine and default schema."""
        self.engine = engine
        self.schema = schema

    def resolve_schema(self, session_id: Optional[str] = None, schema: Optional[str] = None) -> str:
        """Resolves the active database schema name, provisioning a session replica if needed."""
        if schema:
            return schema
        if session_id:
            return ensure_session_replica(self.engine, session_id)
        return self.schema

    def get_table_names(
        self,
        session_id: Optional[str] = None,
        schema: Optional[str] = None,
        _inspector: Optional[Any] = None,
    ) -> List[str]:
        """Retrieves all table and view names present in the target schema."""
        target_schema = self.resolve_schema(session_id=session_id, schema=schema)
        inspector = _inspector if _inspector is not None else inspect(self.engine)
        tables = inspector.get_table_names(schema=target_schema)
        try:
            views = inspector.get_view_names(schema=target_schema)
        except Exception:
            views = []
        return sorted(list(set(tables + views)))

    def get_primary_key_column(
        self,
        table: str,
        session_id: Optional[str] = None,
        schema: Optional[str] = None,
    ) -> Optional[str]:
        """Retrieves the primary key column name for a specified table if defined."""
        target_schema = self.resolve_schema(session_id=session_id, schema=schema)
        try:
            inspector = inspect(self.engine)
            pk_constraint = inspector.get_pk_constraint(table, schema=target_schema)
            constrained_cols = pk_constraint.get("constrained_columns", [])
            return constrained_cols[0] if constrained_cols else None
        except Exception:
            return None

    def get_schema_summary(self, session_id: Optional[str] = None, schema: Optional[str] = None) -> str:
        """Generates a human-readable and LLM-friendly summary of the database schema."""
        target_schema = self.resolve_schema(session_id=session_id, schema=schema)
        inspector = inspect(self.engine)
        tables = self.get_table_names(schema=target_schema, _inspector=inspector)

        if not tables:
            return "No tables found in the active database schema."

        lines: List[str] = ["Database Schema:"]

        for table in tables:
            lines.append(f"\nTable: {table}")
            try:
                columns = inspector.get_columns(table, schema=target_schema)
            except Exception:
                columns = []
            try:
                pk_constraint = inspector.get_pk_constraint(table, schema=target_schema)
                primary_keys = set(pk_constraint.get("constrained_columns", []))
            except Exception:
                primary_keys = set()
            try:
                fks = inspector.get_foreign_keys(table, schema=target_schema)
            except Exception:
                fks = []

            fk_map = {}
            for fk in fks:
                for col, ref_col in zip(fk.get("constrained_columns", []), fk.get("referred_columns", [])):
                    fk_map[col] = f"{fk.get('referred_table')}.{ref_col}"

            for col in columns:
                col_name = col["name"]
                col_type = str(col["type"])
                attributes = []
                if col_name in primary_keys:
                    attributes.append("PRIMARY KEY")
                if not col.get("nullable", True):
                    attributes.append("NOT NULL")
                if col_name in fk_map:
                    attributes.append(f"REFERENCES {fk_map[col_name]}")

                attr_str = f" ({', '.join(attributes)})" if attributes else ""
                lines.append(f"  - {col_name}: {col_type}{attr_str}")

        return "\n".join(lines)
