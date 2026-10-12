import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

import pandas as pd
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import Engine, text

from agents.db_agent.config import get_settings as get_db_settings
from agents.db_agent.db import create_db_engine
from agents.ml_agent.config import MLAgentSettings, get_ml_settings
from agents.ml_agent.prompts import prompt_loader
from agents.ml_agent.runner import MLCodeRunner
from shared.llm.base import BaseLLM, extract_text_from_message_content
from shared.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


class MLAgentState(TypedDict):
    """
    LangGraph state container for the ML Agent execution and self-healing loop.
    """

    task_description: str
    dataset_path: str
    dataset_id: Optional[int]
    resolved_path: str
    dataset_preview: str
    current_code: str
    execution_result: Dict[str, Any]
    error_trace: str
    retry_count: int
    response: str
    success: bool


class MLAgent:
    """
    LangGraph-based Machine Learning Agent that formulates Python code for classical
    data science tasks, executes it in an isolated virtual environment, fixes errors
    via an automated self-healing retry loop, persists interactive Plotly charts and scripts
    into PostgreSQL, and produces ID-only metadata.
    """

    def __init__(
        self,
        llm: BaseLLM,
        runner: MLCodeRunner,
        output_dir: Path,
        max_retries: int = 3,
        engine: Optional[Engine] = None,
    ) -> None:
        self.llm = llm
        self.chat_model: BaseChatModel = llm.get_chat_model()
        self.runner = runner
        self.output_dir = output_dir.resolve()
        self.max_retries = max_retries
        self.engine = engine
        self._ensure_tables()
        self.graph = self._build_graph()

    def _ensure_tables(self) -> None:
        """
        Ensures generated_charts and generated_scripts tables exist in PostgreSQL.
        """
        if not self.engine:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS generated_charts (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255),
                        chart_type VARCHAR(50),
                        spec JSONB NOT NULL,
                        dataset_id INTEGER REFERENCES generated_datasets(id) ON DELETE SET NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS generated_scripts (
                        id SERIAL PRIMARY KEY,
                        script TEXT NOT NULL,
                        language VARCHAR(50) DEFAULT 'python',
                        task_description TEXT,
                        dataset_id INTEGER REFERENCES generated_datasets(id) ON DELETE SET NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))
        except Exception as ex:
            logger.warning(f"Could not initialize tables in MLAgent: {ex}")

    def _build_graph(self) -> Any:
        """
        Constructs and compiles the StateGraph for ML task formulation and execution.
        """
        workflow = StateGraph(MLAgentState)

        workflow.add_node("prepare_dataset", self._prepare_dataset_node)
        workflow.add_node("generate_code", self._generate_code_node)
        workflow.add_node("execute_code", self._execute_code_node)
        workflow.add_node("repair_code", self._repair_code_node)
        workflow.add_node("summarize_results", self._summarize_results_node)

        workflow.add_edge(START, "prepare_dataset")
        workflow.add_edge("prepare_dataset", "generate_code")
        workflow.add_edge("generate_code", "execute_code")
        workflow.add_conditional_edges(
            "execute_code",
            self._route_after_execution,
            {
                "repair": "repair_code",
                "summarize": "summarize_results",
            },
        )
        workflow.add_edge("repair_code", "execute_code")
        workflow.add_edge("summarize_results", END)

        return workflow.compile()

    def _extract_python_code(self, raw_text: str) -> str:
        """
        Extracts executable Python code from markdown code blocks or raw response.
        """
        cleaned = raw_text.strip()
        code_match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()
        return cleaned

    def _resolve_dataset(
        self,
        given_path: Optional[str] = None,
        given_id: Optional[int] = None,
    ) -> Tuple[Path, Optional[int]]:
        """
        Resolves CSV dataset path and matching dataset_id from disk or generated_datasets.
        """
        resolved_path: Optional[Path] = None
        resolved_id: Optional[int] = given_id

        # 1. Lookup by dataset_id if provided
        if resolved_id and self.engine:
            try:
                with self.engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT data, file_path FROM generated_datasets WHERE id = :id"),
                        {"id": resolved_id},
                    ).fetchone()
                    if row:
                        data_val = row[0]
                        file_path_val = row[1]
                        if data_val:
                            if isinstance(data_val, str):
                                data_val = json.loads(data_val)
                            if isinstance(data_val, list) and len(data_val) > 0:
                                df = pd.DataFrame(data_val)
                                temp_csv = self.output_dir / f"dataset_{resolved_id}.csv"
                                df.to_csv(temp_csv, index=False)
                                resolved_path = temp_csv.resolve()
                        if not resolved_path and file_path_val and Path(file_path_val).is_file():
                            resolved_path = Path(file_path_val).resolve()
            except Exception as ex:
                logger.warning(f"Failed to lookup dataset by ID {resolved_id}: {ex}")


        # 2. Lookup by given path
        if not resolved_path and given_path:
            p = Path(given_path)
            if p.is_file():
                resolved_path = p.resolve()
            else:
                candidate = self.output_dir / p.name
                if candidate.is_file():
                    resolved_path = candidate.resolve()

        # 3. Fallback to newest CSV file in output_dir
        if not resolved_path:
            csv_files = sorted(
                list(self.output_dir.glob("*.csv")),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            if csv_files:
                resolved_path = csv_files[0].resolve()
            else:
                resolved_path = (self.output_dir / "dataset.csv").resolve()

        # 4. If dataset_id was not provided, look up by file name in generated_datasets
        if not resolved_id and self.engine and resolved_path.exists():
            try:
                with self.engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT id FROM generated_datasets WHERE file_name = :fn OR file_path = :fp ORDER BY id DESC LIMIT 1"),
                        {"fn": resolved_path.name, "fp": str(resolved_path)},
                    ).fetchone()
                    if row:
                        resolved_id = row[0]
            except Exception as ex:
                logger.debug(f"Could not determine dataset_id: {ex}")

        return resolved_path, resolved_id

    async def _prepare_dataset_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Loads schema, feature types, and data head preview for the dataset.
        """
        dataset_path_str = state.get("dataset_path", "")
        dataset_id = state.get("dataset_id")
        resolved, matched_id = self._resolve_dataset(dataset_path_str, dataset_id)

        preview_lines = []
        if resolved.exists() and resolved.is_file():
            try:
                df = pd.read_csv(resolved)
                preview_lines.append(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")
                preview_lines.append(f"Columns: {list(df.columns)}")
                preview_lines.append("\nColumn Data Types:")
                for col, dt in df.dtypes.items():
                    preview_lines.append(f"- {col}: {dt}")
                preview_lines.append("\nFirst 3 Rows Preview:")
                preview_lines.append(df.head(3).to_string())
            except Exception as ex:
                preview_lines.append(f"Could not load full CSV preview: {ex}")
        else:
            preview_lines.append(f"Dataset path '{resolved}' not found on disk. Code should handle potential missing file gracefully.")

        return {
            "resolved_path": str(resolved),
            "dataset_id": matched_id,
            "dataset_preview": "\n".join(preview_lines),
        }

    async def _generate_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Generates Python machine learning code tailored to the user's task.
        """
        prompt = prompt_loader.render(
            "code_generation",
            task_description=state.get("task_description", ""),
            dataset_path=state.get("resolved_path", ""),
            dataset_preview=state.get("dataset_preview", ""),
            output_dir=str(self.output_dir),
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
        )

        messages = [
            HumanMessage(content=prompt),
        ]
        resp = await self.chat_model.ainvoke(messages)
        content = extract_text_from_message_content(resp.content)
        code = self._extract_python_code(content)

        return {
            "current_code": code,
        }

    async def _execute_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Executes current code in the isolated subprocess runner.
        """
        code = state.get("current_code", "")
        res = await self.runner.run_code(code)

        return {
            "execution_result": res,
            "error_trace": res.get("error_trace", ""),
            "success": res.get("success", False),
        }

    def _route_after_execution(self, state: MLAgentState) -> Literal["repair", "summarize"]:
        """
        Routes to repair loop if execution failed and retries remain, else proceeds to summarize.
        """
        if not state.get("success") and state.get("retry_count", 0) < self.max_retries:
            return "repair"
        return "summarize"

    async def _repair_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Self-healing node: debugs and repairs code based on execution traceback.
        """
        current_retries = state.get("retry_count", 0) + 1
        logger.info(f"MLAgent self-healing repair attempt {current_retries}/{self.max_retries}")

        prompt = prompt_loader.render(
            "code_repair",
            task_description=state.get("task_description", ""),
            dataset_path=state.get("resolved_path", ""),
            dataset_preview=state.get("dataset_preview", ""),
            output_dir=str(self.output_dir),
            current_code=state.get("current_code", ""),
            error_trace=state.get("error_trace", ""),
            timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
        )

        messages = [
            HumanMessage(content=prompt),
        ]
        resp = await self.chat_model.ainvoke(messages)
        content = extract_text_from_message_content(resp.content)
        fixed_code = self._extract_python_code(content)

        return {
            "current_code": fixed_code,
            "retry_count": current_retries,
        }

    async def _summarize_results_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Synthesizes final analytical summary from code output and generated Plotly charts.
        """
        exec_res = state.get("execution_result", {})
        stdout = exec_res.get("stdout", "")
        charts = exec_res.get("charts", [])
        plots = exec_res.get("plots", [])
        success = state.get("success", False)

        if not success:
            error_summary = (
                f"### Machine Learning Execution Failed\n\n"
                f"The generated code could not execute successfully after {state.get('retry_count', 0)} attempts.\n\n"
                f"**Error Details:**\n```\n{state.get('error_trace', '')}\n```"
            )
            return {"response": error_summary}

        prompt = prompt_loader.render(
            "summary",
            task_description=state.get("task_description", ""),
            stdout=stdout,
            charts=charts,
            plots=plots,
        )

        messages = [
            HumanMessage(content=prompt),
        ]
        resp = await self.chat_model.ainvoke(messages)
        summary_text = extract_text_from_message_content(resp.content)

        return {
            "response": summary_text,
        }

    def _save_charts_to_db(self, charts: List[Dict[str, Any]], dataset_id: Optional[int] = None) -> List[int]:
        """
        Persists generated Plotly chart JSON specifications into PostgreSQL generated_charts.
        """
        if not self.engine or not charts:
            return []

        chart_ids: List[int] = []
        for ch in charts:
            spec = ch.get("spec", {})
            title = ""
            if isinstance(spec, dict):
                layout_title = spec.get("layout", {}).get("title")
                if isinstance(layout_title, dict):
                    title = layout_title.get("text", "")
                elif isinstance(layout_title, str):
                    title = layout_title
            if not title:
                title = ch.get("file_name", "Plotly Chart").replace(".json", "").replace("_", " ").title()

            chart_type = "plotly"
            if isinstance(spec, dict) and "data" in spec and isinstance(spec["data"], list) and len(spec["data"]) > 0:
                first_trace = spec["data"][0]
                if isinstance(first_trace, dict):
                    chart_type = first_trace.get("type", "plotly")

            try:
                with self.engine.begin() as conn:
                    res = conn.execute(
                        text("""
                            INSERT INTO generated_charts (title, chart_type, spec, dataset_id)
                            VALUES (:title, :chart_type, :spec, :dataset_id)
                            RETURNING id
                        """),
                        {
                            "title": str(title)[:255],
                            "chart_type": str(chart_type)[:50],
                            "spec": json.dumps(spec),
                            "dataset_id": dataset_id,
                        },
                    )
                    new_id = res.scalar()
                    if new_id:
                        chart_ids.append(new_id)
            except Exception as ex:
                logger.error(f"Error saving chart to database: {ex}", exc_info=True)

        return chart_ids

    def _save_script_to_db(self, script: str, task_description: str, dataset_id: Optional[int] = None) -> Optional[int]:
        """
        Persists generated ML Python code into PostgreSQL generated_scripts.
        """
        if not self.engine or not script.strip():
            return None

        try:
            with self.engine.begin() as conn:
                res = conn.execute(
                    text("""
                        INSERT INTO generated_scripts (script, language, task_description, dataset_id)
                        VALUES (:script, 'python', :task_description, :dataset_id)
                        RETURNING id
                    """),
                    {
                        "script": script,
                        "task_description": task_description,
                        "dataset_id": dataset_id,
                    },
                )
                return res.scalar()
        except Exception as ex:
            logger.error(f"Error saving script to database: {ex}", exc_info=True)
            return None

    async def run(
        self,
        task_description: str,
        dataset_path: Optional[str] = None,
        dataset_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Runs the full end-to-end ML Agent workflow asynchronously, returning response
        and ID-only metadata.

        Args:
            task_description (str): Natural language task requirement.
            dataset_path (Optional[str]): Path to CSV dataset file.
            dataset_id (Optional[int]): Database identifier of the dataset.

        Returns:
            Dict[str, Any]: Structured dictionary with response text and ID-only metadata.
        """
        initial_state: MLAgentState = {
            "task_description": task_description,
            "dataset_path": dataset_path or "",
            "dataset_id": dataset_id,
            "resolved_path": "",
            "dataset_preview": "",
            "current_code": "",
            "execution_result": {},
            "error_trace": "",
            "retry_count": 0,
            "response": "",
            "success": False,
        }

        final_state = await self.graph.ainvoke(initial_state)
        exec_res = final_state.get("execution_result") or {}
        resolved_dataset_id = final_state.get("dataset_id")

        charts = exec_res.get("charts", [])
        chart_ids = self._save_charts_to_db(charts, dataset_id=resolved_dataset_id)

        code_script = final_state.get("current_code", "")
        script_id = self._save_script_to_db(code_script, task_description, dataset_id=resolved_dataset_id)

        metadata: Dict[str, Any] = {}
        if chart_ids:
            metadata["chart_id"] = chart_ids[0]
            if len(chart_ids) > 1:
                metadata["chart_ids"] = chart_ids
        if script_id:
            metadata["script_id"] = script_id
        if resolved_dataset_id:
            metadata["dataset_id"] = resolved_dataset_id

        return {
            "response": final_state.get("response", ""),
            "metadata": metadata,
        }

    def run_sync(
        self,
        task_description: str,
        dataset_path: Optional[str] = None,
        dataset_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous execution helper.
        """
        try:
            return asyncio.run(self.run(task_description=task_description, dataset_path=dataset_path, dataset_id=dataset_id))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.run(task_description=task_description, dataset_path=dataset_path, dataset_id=dataset_id))


def create_ml_agent(settings: Optional[MLAgentSettings] = None, engine: Optional[Engine] = None) -> MLAgent:
    """
    Factory function to construct and configure a fully functional MLAgent.
    """
    cfg = settings or get_ml_settings()
    python_bin = cfg.resolve_python_executable()

    runner = MLCodeRunner(
        python_bin=python_bin,
        output_dir=cfg.output_dir,
        timeout_seconds=cfg.execution_timeout_seconds,
    )

    active_llm = LLMFactory.create(
        provider=cfg.llm_provider,
        api_key=cfg.llm_api_key or None,
        model_name=cfg.llm_model,
    )

    db_engine = engine
    if db_engine is None:
        try:
            db_cfg = get_db_settings()
            db_engine = create_db_engine(db_cfg.database_url)
        except Exception as e:
            logger.warning(f"Could not initialize DB engine for MLAgent: {e}")

    return MLAgent(
        llm=active_llm,
        runner=runner,
        output_dir=cfg.output_dir,
        max_retries=cfg.max_retries,
        engine=db_engine,
    )


build_ml_agent = create_ml_agent
