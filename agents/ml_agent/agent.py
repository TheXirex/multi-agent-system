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
from agents.ml_agent.runner import MLCodeRunner, sanitize_code_comments
from shared.llm.base import BaseLLM, extract_text_from_message_content
from shared.llm.factory import LLMFactory
from shared.metadata import build_domain_metadata

logger = logging.getLogger(__name__)


class MLAgentState(TypedDict):
    """
    LangGraph state container for the ML Agent execution and self-healing loop.
    """

    task_description: str
    dataset_path: str
    dataset_id: Optional[int]
    dataset_ids: Optional[List[int]]
    session_id: Optional[str]
    in_memory_datasets: Dict[str, Any]
    is_multi_dataset: bool
    copy_instructions: str
    resolved_path: str
    dataset_preview: str
    current_code: str
    execution_result: Dict[str, Any]
    error_trace: str
    retry_count: int
    response: str
    success: bool
    needs_clarification: bool
    clarification_questions: List[Dict[str, Any]]


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
        Ensures generated_charts and generated_scripts tables exist in PostgreSQL with session_id support.
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
                        session_id VARCHAR(36),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    ALTER TABLE generated_charts ADD COLUMN IF NOT EXISTS session_id VARCHAR(36);
                    CREATE INDEX IF NOT EXISTS idx_generated_charts_session_id ON generated_charts(session_id);

                    CREATE TABLE IF NOT EXISTS generated_scripts (
                        id SERIAL PRIMARY KEY,
                        script TEXT NOT NULL,
                        language VARCHAR(50) DEFAULT 'python',
                        task_description TEXT,
                        dataset_id INTEGER REFERENCES generated_datasets(id) ON DELETE SET NULL,
                        session_id VARCHAR(36),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    ALTER TABLE generated_scripts ADD COLUMN IF NOT EXISTS session_id VARCHAR(36);
                    CREATE INDEX IF NOT EXISTS idx_generated_scripts_session_id ON generated_scripts(session_id);
                """))
        except Exception as ex:
            logger.warning(f"Could not initialize tables in MLAgent: {ex}")

    def _build_graph(self) -> Any:
        """
        Constructs and compiles the StateGraph for ML task formulation and execution.
        """
        workflow = StateGraph(MLAgentState)

        workflow.add_node("prepare_dataset", self._prepare_dataset_node)
        workflow.add_node("check_clarity", self._check_clarity_node)
        workflow.add_node("generate_code", self._generate_code_node)
        workflow.add_node("execute_code", self._execute_code_node)
        workflow.add_node("repair_code", self._repair_code_node)
        workflow.add_node("summarize_results", self._summarize_results_node)

        workflow.add_edge(START, "prepare_dataset")
        workflow.add_edge("prepare_dataset", "check_clarity")
        workflow.add_conditional_edges(
            "check_clarity",
            self._route_after_clarity,
            {
                "clarify": END,
                "proceed": "generate_code",
            },
        )
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

    def _clean_identifier(self, name: str) -> str:
        """
        Transforms dataset or sheet name into a clean Python variable identifier.
        """
        cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")
        if not cleaned or cleaned[0].isdigit():
            cleaned = f"ds_{cleaned}"
        return cleaned

    def _resolve_in_memory_datasets(
        self,
        given_path: Optional[str] = None,
        given_id: Optional[int] = None,
        given_ids: Optional[List[int]] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[Dict[str, pd.DataFrame], Optional[int], List[int]]:
        """
        Loads dataset records directly into memory as pandas DataFrames without writing CSVs to disk.
        Supports single and multiple datasets, scoped strictly to the given session_id when provided.
        """
        loaded_dfs: Dict[str, pd.DataFrame] = {}
        target_ids: List[int] = []
        if given_ids:
            target_ids = [int(i) for i in given_ids]
        elif given_id:
            target_ids = [int(given_id)]

        if target_ids and self.engine:
            try:
                with self.engine.connect() as conn:
                    if session_id:
                        query_sql = text("""
                            SELECT id, name, data FROM generated_datasets
                            WHERE id = ANY(:ids) AND (session_id = :session_id OR session_id IS NULL)
                            ORDER BY id ASC
                        """)
                        query_params = {"ids": target_ids, "session_id": session_id}
                    else:
                        query_sql = text("SELECT id, name, data FROM generated_datasets WHERE id = ANY(:ids) ORDER BY id ASC")
                        query_params = {"ids": target_ids}

                    rows = conn.execute(query_sql, query_params).fetchall()
                    resolved_ids: List[int] = []
                    for r in rows:
                        ds_id, ds_name, raw_data = r[0], r[1], r[2]
                        resolved_ids.append(ds_id)
                        if isinstance(raw_data, str):
                            raw_data = json.loads(raw_data)
                        if isinstance(raw_data, list):
                            df = pd.DataFrame(raw_data)
                            loaded_dfs[f"data_{ds_id}"] = df
                            clean_var = f"data_{self._clean_identifier(ds_name)}"
                            loaded_dfs[clean_var] = df
                    target_ids = resolved_ids
            except Exception as ex:
                logger.warning(f"Failed to lookup datasets by IDs {target_ids}: {ex}")
                target_ids = []

        # If not resolved by ID, try given_path
        if not loaded_dfs and given_path:
            p = Path(given_path)
            if p.is_file():
                try:
                    ext = p.suffix.lower()
                    if ext == ".csv":
                        df = pd.read_csv(p)
                        loaded_dfs["data"] = df
                    elif ext in (".xlsx", ".xls"):
                        xl = pd.ExcelFile(p)
                        for sname in xl.sheet_names:
                            sheet_df = pd.read_excel(xl, sheet_name=sname)
                            clean_var = f"data_{self._clean_identifier(sname)}"
                            loaded_dfs[clean_var] = sheet_df
                except Exception as ex:
                    logger.warning(f"Failed to read dataset from path '{given_path}': {ex}")

        # If still empty, query latest dataset from generated_datasets scoped to session_id if provided
        if not loaded_dfs and self.engine:
            try:
                with self.engine.connect() as conn:
                    if session_id:
                        row = conn.execute(
                            text("SELECT id, name, data FROM generated_datasets WHERE session_id = :session_id ORDER BY id DESC LIMIT 1"),
                            {"session_id": session_id},
                        ).fetchone()
                    else:
                        row = conn.execute(
                            text("SELECT id, name, data FROM generated_datasets ORDER BY id DESC LIMIT 1")
                        ).fetchone()

                    if row:
                        ds_id, ds_name, raw_data = row[0], row[1], row[2]
                        if isinstance(raw_data, str):
                            raw_data = json.loads(raw_data)
                        if isinstance(raw_data, list):
                            df = pd.DataFrame(raw_data)
                            loaded_dfs["data"] = df
                            loaded_dfs[f"data_{ds_id}"] = df
                            target_ids = [ds_id]
                    else:
                        target_ids = []
            except Exception as ex:
                logger.debug(f"Could not load latest dataset from database: {ex}")
                target_ids = []

        actual_ids = target_ids if loaded_dfs else []
        primary_id = actual_ids[0] if actual_ids else None
        return loaded_dfs, primary_id, actual_ids

    async def _prepare_dataset_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Loads schema, feature types, and data preview for in-memory datasets.
        """
        given_path = state.get("dataset_path", "")
        given_id = state.get("dataset_id")
        given_ids = state.get("dataset_ids")
        sess_id = state.get("session_id")

        loaded_dfs, matched_id, all_ids = self._resolve_in_memory_datasets(
            given_path=given_path,
            given_id=given_id,
            given_ids=given_ids,
            session_id=sess_id,
        )

        if not loaded_dfs:
            loaded_dfs = {"data": pd.DataFrame()}

        # Distinguish unique DataFrames
        unique_dfs: List[Tuple[str, pd.DataFrame]] = []
        seen_ids = set()
        for k, v in loaded_dfs.items():
            df_id = id(v)
            if df_id not in seen_ids:
                seen_ids.add(df_id)
                unique_dfs.append((k, v))

        is_multi = len(unique_dfs) > 1
        preview_sections = []
        copy_stmts = []

        if not is_multi:
            var_name, df = unique_dfs[0]
            loaded_dfs["data"] = df
            copy_stmts.append("df = data.copy()")
            preview_sections.append(f"In-memory DataFrame: `data`\nShape: {df.shape[0]} rows, {df.shape[1]} columns")
            preview_sections.append(f"Columns: {list(df.columns)}")
            preview_sections.append("Column Data Types:")
            for col, dt in df.dtypes.items():
                preview_sections.append(f"- {col}: {dt}")
            preview_sections.append("First 3 Rows Preview:")
            preview_sections.append(df.head(3).to_string())
        else:
            for idx, (var_name, df) in enumerate(unique_dfs, start=1):
                idx_var = f"data_{idx}"
                loaded_dfs[idx_var] = df
                clean_name = var_name.replace("data_", "")
                copy_stmts.append(f"df_{clean_name} = {var_name}.copy()  # or {idx_var}.copy()")
                preview_sections.append(f"--- Dataset #{idx}: `{idx_var}` / `{var_name}` ---")
                preview_sections.append(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")
                preview_sections.append(f"Columns: {list(df.columns)}")
                preview_sections.append("Column Data Types:")
                for col, dt in df.dtypes.items():
                    preview_sections.append(f"- {col}: {dt}")
                preview_sections.append("First 2 Rows Preview:")
                preview_sections.append(df.head(2).to_string())
                preview_sections.append("")

            # Set 'data' as alias to first dataset for safety
            loaded_dfs["data"] = unique_dfs[0][1]

        return {
            "in_memory_datasets": loaded_dfs,
            "dataset_id": matched_id,
            "dataset_ids": all_ids,
            "is_multi_dataset": is_multi,
            "copy_instructions": "\n".join(copy_stmts),
            "dataset_preview": "\n".join(preview_sections),
            "resolved_path": "",
        }

    async def _check_clarity_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Evaluates if the user's task description is clear or if specific clarification is needed.
        """
        task_desc = state.get("task_description", "")
        dataset_preview = state.get("dataset_preview", "")

        prompt = prompt_loader.render(
            "task_clarity",
            task_description=task_desc,
            dataset_preview=dataset_preview,
        )

        try:
            resp = await self.chat_model.ainvoke([HumanMessage(content=prompt)])
            text_content = extract_text_from_message_content(resp.content)

            json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text_content)
            json_str = json_match.group(1) if json_match else text_content
            data = json.loads(json_str)

            needs_clarification = bool(data.get("needs_clarification", False))
            questions = data.get("questions", [])

            if needs_clarification and questions:
                lines = [
                    "### Clarification Needed Before Training ML Model\n",
                    "To build the most accurate and suitable model, please clarify the following questions or pick from the recommended options:\n",
                ]
                for idx, q in enumerate(questions, start=1):
                    q_text = q.get("question", "")
                    rec = q.get("recommended", "")
                    opts = q.get("options", [])
                    lines.append(f"**{idx}. {q_text}**")
                    if rec:
                        lines.append(f"- **Recommended:** {rec}")
                    if opts:
                        opts_str = ", ".join(f"`{o}`" for o in opts)
                        lines.append(f"- *Available options:* {opts_str}")
                    lines.append("")

                formatted_resp = "\n".join(lines).strip()
                return {
                    "needs_clarification": True,
                    "clarification_questions": questions,
                    "response": formatted_resp,
                }
        except Exception as ex:
            logger.warning(f"Clarity check failed or returned invalid JSON ({ex}), proceeding to code generation")

        return {
            "needs_clarification": False,
            "clarification_questions": [],
        }

    def _route_after_clarity(self, state: MLAgentState) -> Literal["clarify", "proceed"]:
        """
        Routes to end if clarification is required, otherwise continues to code generation.
        """
        if state.get("needs_clarification"):
            return "clarify"
        return "proceed"

    async def _generate_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Generates Python machine learning code tailored to the user's task.
        """
        prompt = prompt_loader.render(
            "code_generation",
            task_description=state.get("task_description", ""),
            dataset_preview=state.get("dataset_preview", ""),
            output_dir=str(self.output_dir),
            is_multi_dataset=state.get("is_multi_dataset", False),
            copy_instructions=state.get("copy_instructions", "df = data.copy()"),
        )

        messages = [
            HumanMessage(content=prompt),
        ]
        resp = await self.chat_model.ainvoke(messages)
        content = extract_text_from_message_content(resp.content)
        code = self._extract_python_code(content)
        clean_code = sanitize_code_comments(code)

        return {
            "current_code": clean_code,
        }

    async def _execute_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """
        Executes current code in the isolated subprocess runner with in-memory datasets.
        """
        code = state.get("current_code", "")
        in_memory_dfs = state.get("in_memory_datasets", {})
        res = await self.runner.run_code(code, in_memory_datasets=in_memory_dfs)

        return {
            "execution_result": res,
            "error_trace": res.get("error_trace", ""),
            "success": res.get("success", False),
            "current_code": res.get("code", code),
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
            dataset_preview=state.get("dataset_preview", ""),
            output_dir=str(self.output_dir),
            current_code=state.get("current_code", ""),
            error_trace=state.get("error_trace", ""),
            is_multi_dataset=state.get("is_multi_dataset", False),
            copy_instructions=state.get("copy_instructions", "df = data.copy()"),
        )

        messages = [
            HumanMessage(content=prompt),
        ]
        resp = await self.chat_model.ainvoke(messages)
        content = extract_text_from_message_content(resp.content)
        fixed_code = self._extract_python_code(content)
        clean_fixed_code = sanitize_code_comments(fixed_code)

        return {
            "current_code": clean_fixed_code,
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

    def _save_charts_to_db(
        self,
        charts: List[Dict[str, Any]],
        dataset_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> List[int]:
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
                raw_title = ch.get("file_name", "Plotly Chart").replace(".json", "").replace("_", " ")
                clean_title = re.sub(r"\b\d{8}[-_]?\d{4,6}\b", "", raw_title).strip()
                title = clean_title.title() if clean_title else "Plotly Chart"

            chart_type = "plotly"
            if isinstance(spec, dict) and "data" in spec and isinstance(spec["data"], list) and len(spec["data"]) > 0:
                first_trace = spec["data"][0]
                if isinstance(first_trace, dict):
                    chart_type = first_trace.get("type", "plotly")

            try:
                with self.engine.begin() as conn:
                    res = conn.execute(
                        text("""
                            INSERT INTO generated_charts (title, chart_type, spec, dataset_id, session_id)
                            VALUES (:title, :chart_type, :spec, :dataset_id, :session_id)
                            RETURNING id
                        """),
                        {
                            "title": str(title)[:255],
                            "chart_type": str(chart_type)[:50],
                            "spec": json.dumps(spec),
                            "dataset_id": dataset_id,
                            "session_id": session_id,
                        },
                    )
                    new_id = res.scalar()
                    if new_id:
                        chart_ids.append(new_id)
            except Exception as ex:
                logger.error(f"Error saving chart to database: {ex}", exc_info=True)

        return chart_ids

    def _save_script_to_db(
        self,
        script: str,
        task_description: str,
        dataset_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Persists generated ML Python code into PostgreSQL generated_scripts.
        """
        if not self.engine or not script.strip():
            return None

        try:
            with self.engine.begin() as conn:
                res = conn.execute(
                    text("""
                        INSERT INTO generated_scripts (script, language, task_description, dataset_id, session_id)
                        VALUES (:script, 'python', :task_description, :dataset_id, :session_id)
                        RETURNING id
                    """),
                    {
                        "script": script,
                        "task_description": task_description,
                        "dataset_id": dataset_id,
                        "session_id": session_id,
                    },
                )
                return res.scalar()
        except Exception as ex:
            logger.error(f"Error saving script to database: {ex}", exc_info=True)
            return None

    def _cleanup_intermediate_files(self) -> None:
        """
        Deletes all intermediate files (CSVs, JSON chart specs, python scripts, plots)
        from disk immediately once intermediate execution stages are complete, ensuring
        no traces remain in the local filesystem.
        """
        try:
            if self.output_dir.exists():
                for p in self.output_dir.iterdir():
                    if p.is_file():
                        try:
                            p.unlink(missing_ok=True)
                        except Exception as ex:
                            logger.debug(f"Could not delete temp file {p.name}: {ex}")
            scripts_dir = self.output_dir / "ml_scripts"
            if scripts_dir.exists():
                for p in scripts_dir.iterdir():
                    if p.is_file():
                        try:
                            p.unlink(missing_ok=True)
                        except Exception as ex:
                            logger.debug(f"Could not delete script file {p.name}: {ex}")
        except Exception as ex:
            logger.debug(f"Error during intermediate file cleanup: {ex}")

    async def run(
        self,
        task_description: str,
        dataset_path: Optional[str] = None,
        dataset_id: Optional[int] = None,
        dataset_ids: Optional[List[int]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs the full end-to-end ML Agent workflow asynchronously, returning response
        and ID-only metadata. Cleans up all intermediate files from disk once finished.

        Args:
            task_description (str): Natural language task requirement.
            dataset_path (Optional[str]): Path to CSV dataset file.
            dataset_id (Optional[int]): Database identifier of the dataset.
            dataset_ids (Optional[List[int]]): Optional list of multiple dataset identifiers.
            session_id (Optional[str]): Optional session ID to bind and scope the analysis.

        Returns:
            Dict[str, Any]: Structured dictionary with response text and ID-only metadata.
        """
        initial_state: MLAgentState = {
            "task_description": task_description,
            "dataset_path": dataset_path or "",
            "dataset_id": dataset_id,
            "dataset_ids": dataset_ids,
            "session_id": session_id,
            "in_memory_datasets": {},
            "is_multi_dataset": False,
            "copy_instructions": "df = data.copy()",
            "resolved_path": "",
            "dataset_preview": "",
            "current_code": "",
            "execution_result": {},
            "error_trace": "",
            "retry_count": 0,
            "response": "",
            "success": False,
            "needs_clarification": False,
            "clarification_questions": [],
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)

            if final_state.get("needs_clarification"):
                return {
                    "response": final_state.get("response", ""),
                    "metadata": build_domain_metadata(
                        status="clarification_needed",
                        questions=final_state.get("clarification_questions", []),
                        dataset_id=final_state.get("dataset_id"),
                        dataset_ids=final_state.get("dataset_ids"),
                    ),
                }

            exec_res = final_state.get("execution_result") or {}
            resolved_dataset_id = final_state.get("dataset_id")
            resolved_dataset_ids = final_state.get("dataset_ids")
            resolved_sess_id = final_state.get("session_id")

            charts = exec_res.get("charts", [])
            chart_ids = self._save_charts_to_db(charts, dataset_id=resolved_dataset_id, session_id=resolved_sess_id)

            code_script = final_state.get("current_code", "")
            script_id = self._save_script_to_db(code_script, task_description, dataset_id=resolved_dataset_id, session_id=resolved_sess_id)

            metadata = build_domain_metadata(
                chart_ids=chart_ids,
                script_id=script_id,
                dataset_id=resolved_dataset_id,
                dataset_ids=resolved_dataset_ids,
                code=code_script,
            )

            return {
                "response": final_state.get("response", ""),
                "metadata": metadata,
            }
        finally:
            self._cleanup_intermediate_files()

    def run_sync(
        self,
        task_description: str,
        dataset_path: Optional[str] = None,
        dataset_id: Optional[int] = None,
        dataset_ids: Optional[List[int]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous execution helper.
        """
        try:
            return asyncio.run(
                self.run(
                    task_description=task_description,
                    dataset_path=dataset_path,
                    dataset_id=dataset_id,
                    dataset_ids=dataset_ids,
                    session_id=session_id,
                )
            )
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.run(
                    task_description=task_description,
                    dataset_path=dataset_path,
                    dataset_id=dataset_id,
                    dataset_ids=dataset_ids,
                    session_id=session_id,
                )
            )


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
