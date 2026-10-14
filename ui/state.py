from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StudioState:
    """
    Central reactive state container for the DB Studio web application.
    """
    current_session_id: Optional[str] = None
    current_session_title: str = "New Session"
    is_busy: bool = False

    # Active workspace artifacts (latest dataset, charts, scripts)
    current_dataset_rows: List[Dict[str, Any]] = field(default_factory=list)
    current_dataset_columns: List[Dict[str, Any]] = field(default_factory=list)
    current_dataset_name: Optional[str] = None
    current_dataset_id: Optional[int] = None

    current_charts: List[Dict[str, Any]] = field(default_factory=list)
    current_python_script: Optional[str] = None
    current_sql_query: Optional[str] = None

    def reset_workspace(self) -> None:
        """
        Clears workspace state when switching to a session without artifacts.
        """
        self.current_dataset_rows = []
        self.current_dataset_columns = []
        self.current_dataset_name = None
        self.current_dataset_id = None
        self.current_charts = []
        self.current_python_script = None
        self.current_sql_query = None
