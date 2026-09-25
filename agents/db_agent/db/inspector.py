from typing import List
from sqlalchemy import Engine, inspect


class DatabaseInspector:
    """
    Inspects database tables, columns, and relationships to provide schema context.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_table_names(self) -> List[str]:
        """
        Retrieves all table names present in the default database schema.

        Args:
            None

        Returns:
            List[str]: List of table names found in the database.
        """
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def get_schema_summary(self) -> str:
        """
        Generates a human-readable and LLM-friendly summary of the database schema.

        Args:
            None

        Returns:
            str: Formatted description of tables, columns, types, and foreign keys.
        """
        inspector = inspect(self.engine)
        tables = inspector.get_table_names()

        if not tables:
            return "No tables found in the database."

        lines: List[str] = ["Database Schema:"]

        for table in tables:
            lines.append(f"\nTable: {table}")
            columns = inspector.get_columns(table)
            pk_constraint = inspector.get_pk_constraint(table)
            primary_keys = set(pk_constraint.get("constrained_columns", []))
            fks = inspector.get_foreign_keys(table)

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
