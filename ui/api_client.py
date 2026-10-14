import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")


class DBStudioClient:
    """
    HTTP client for interacting with the AI FastAPI service endpoints:
    sessions, queries, datasets, interactive Plotly charts, and scripts.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url: str = (base_url or AI_SERVICE_URL).rstrip("/")

    async def fetch_sessions(self) -> List[Dict[str, Any]]:
        """
        Retrieves all chat sessions from PostgreSQL backend.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/api/sessions")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            logger.warning(f"Error fetching sessions: {ex}")
        return []

    async def create_session(self, title: str = "New Session") -> Optional[Dict[str, Any]]:
        """
        Creates a new chat session in the database.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/sessions",
                    json={"title": title},
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            logger.warning(f"Error creating session: {ex}")
        return None

    async def get_session_detail(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves full details and message history of a chat session.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.base_url}/api/sessions/{session_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            logger.warning(f"Error fetching session detail {session_id}: {ex}")
        return None

    async def delete_session(self, session_id: str) -> bool:
        """
        Deletes a chat session and its history from the database.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.delete(f"{self.base_url}/api/sessions/{session_id}")
                return resp.status_code == 200
        except Exception as ex:
            logger.warning(f"Error deleting session {session_id}: {ex}")
        return False

    async def update_session_title(self, session_id: str, title: str) -> bool:
        """
        Renames a chat session.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.patch(
                    f"{self.base_url}/api/sessions/{session_id}",
                    json={"title": title},
                )
                return resp.status_code == 200
        except Exception as ex:
            logger.warning(f"Error updating session {session_id}: {ex}")
        return False

    async def send_query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends natural language query to the AI service endpoint with session memory.
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/query",
                json={"query": query_text, "session_id": session_id},
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_dataset(self, dataset_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches dataset metadata and rows from backend by dataset_id.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.base_url}/api/datasets/{dataset_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            logger.warning(f"Error fetching dataset {dataset_id}: {ex}")
        return None

    async def fetch_chart(self, chart_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches Plotly chart JSON specification from backend by chart_id.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.base_url}/api/charts/{chart_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            logger.warning(f"Error fetching chart {chart_id}: {ex}")
        return None

    async def fetch_script(self, script_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches script content from backend by script_id.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.base_url}/api/scripts/{script_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            logger.warning(f"Error fetching script {script_id}: {ex}")
        return None
