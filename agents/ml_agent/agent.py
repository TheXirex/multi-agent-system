import asyncio
import contextvars
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

import pandas as pd
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import Engine, text

from agents.db_agent.config import get_settings as get_db_settings
from agents.db_agent.db import create_db_engine
from agents.ml_agent.config import MLAgentSettings, get_ml_settings
from agents.ml_agent.prompts import prompt_loader
from agents.ml_agent.runner import MLCodeRunner
from agents.ml_agent.utils.schemas import MLCodeGenerationOutput, TaskClarityOutput
from shared.db import apply_session_search_path, get_session_schema_or_public
from shared.llm.base import BaseLLM, extract_text_from_message_content
from shared.llm.factory import LLMFactory
from shared.metadata import build_domain_metadata, truncate_words
from shared.observability import (
    create_trace,
    flush_langfuse,
    trace_span,
)

logger = logging.getLogger(__name__)

# Context variable to hold active Langfuse trace for ml_agent
_current_ml_trace: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "_current_ml_trace", default=None
)


class MLAgentState(TypedDict):
    """
    LangGraph state container for the ML Agent execution and self-healing loop.
    """

    task_description: str
    code_title: str
    dataset_path: str
    dataset_id: Optional[int]
    dataset_ids: Optional[List[int]]
    table_names: Optional[List[str]]
    session_id: Optional[str]
    sql_query: Optional[str]
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


def _is_color_title(val: Any) -> bool:
    """Checks whether a legend or colorbar title is a redundant generic 'color' label."""
    if not isinstance(val, str):
        return False
    s = val.strip().lower()
    if s.startswith("<b>") and s.endswith("</b>"):
        s = s[3:-4].strip()
    if s.startswith("<span>") and s.endswith("</span>"):
        s = s[6:-7].strip()
    return s in ("color", "colour", "color:", "colour:")


def _clear_color_title_field(container: Dict[str, Any], key: str) -> None:
    """Clears a title field inside a dictionary if it contains a generic 'color' label."""
    field_val = container.get(key)
    if isinstance(field_val, dict):
        if _is_color_title(field_val.get("text")):
            field_val["text"] = ""
    elif _is_color_title(field_val):
        container[key] = ""


def _clean_chart_spec(spec: Dict[str, Any]) -> None:
    """Sanitizes a Plotly figure specification in-place by removing duplicate titles and generic 'color' labels."""
    if not isinstance(spec, dict):
        return

    layout = spec.get("layout")
    if isinstance(layout, dict):
        if "title" in layout:
            if isinstance(layout["title"], dict):
                layout["title"]["text"] = ""
            else:
                layout["title"] = ""

        legend = layout.get("legend")
        if isinstance(legend, dict):
            _clear_color_title_field(legend, "title")

        _clear_color_title_field(layout, "legend_title_text")
        _clear_color_title_field(layout, "legend_title")

        template = layout.get("template")
        if isinstance(template, dict):
            t_layout = template.get("layout")
            if isinstance(t_layout, dict):
                t_legend = t_layout.get("legend")
                if isinstance(t_legend, dict):
                    _clear_color_title_field(t_legend, "title")
                _clear_color_title_field(t_layout, "legend_title_text")

    data = spec.get("data")
    if isinstance(data, list):
        for trace in data:
            if isinstance(trace, dict):
                marker = trace.get("marker")
                if isinstance(marker, dict):
                    colorbar = marker.get("colorbar")
                    if isinstance(colorbar, dict):
                        _clear_color_title_field(colorbar, "title")


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
        max_retries: int = 3,
        engine: Optional[Engine] = None,
    ) -> None:
        """
        Initializes the Machine Learning Agent.

        Args:
            llm (BaseLLM): Configured language model wrapper.
            runner (MLCodeRunner): Subprocess execution sandbox runner.
            max_retries (int): Maximum self-healing code repair attempts.
            engine (Optional[Engine]): Optional SQLAlchemy database engine for loading tables and persisting artifacts.
        """
        self.llm = llm
        self.chat_model: BaseChatModel = llm.get_chat_model()
        self.runner = runner
        self.max_retries = max_retries
        self.engine = engine
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Constructs and compiles the StateGraph for ML task formulation and execution."""
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
        """Extracts executable Python code from markdown code blocks or raw LLM output."""
        cleaned = raw_text.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for i in range(1, len(parts), 2):
                block = parts[i]
                if block.lower().startswith("python"):
                    block = block[6:]
                elif block.lower().startswith("py"):
                    block = block[2:]
                extracted = block.strip()
                if extracted:
                    return extracted
        return cleaned

    def _clean_identifier(self, name: str) -> str:
        """Transforms a dataset or sheet name into a clean Python variable identifier."""
        cleaned = "".join(c if (c.isalnum() or c == "_") else "_" for c in name.lower()).strip("_")
        if not cleaned or cleaned[0].isdigit():
            cleaned = f"ds_{cleaned}"
        return cleaned

    def _resolve_in_memory_datasets(
        self,
        given_path: Optional[str] = None,
        given_id: Optional[int] = None,
        given_ids: Optional[List[int]] = None,
        table_names: Optional[Any] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[Dict[str, pd.DataFrame], Optional[int], List[int], Optional[str]]:
        """
        Loads dataset records directly into memory as pandas DataFrames.
        Prioritizes querying the specified relational SQL table(s) in the active session schema,
        falling back to a local file path or all base tables in the target schema.

        Args:
            given_path (Optional[str]): Optional path to a CSV or Excel file on disk.
            given_id (Optional[int]): Optional legacy dataset ID.
            given_ids (Optional[List[int]]): Optional list of legacy dataset IDs.
            table_names (Optional[Any]): Table name or list of table names to load.
            session_id (Optional[str]): Active session ID for session schema resolution.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            Tuple[Dict[str, pd.DataFrame], Optional[int], List[int], Optional[str]]:
                Mapping of variable names to DataFrames, primary dataset ID, all dataset IDs, and executed SQL string.
        """
        loaded_dfs: Dict[str, pd.DataFrame] = {}
        executed_sql: Optional[str] = None

        # 1. Normalize table_names
        resolved_tables: List[str] = []
        if isinstance(table_names, str):
            resolved_tables = [table_names]
        elif isinstance(table_names, list):
            resolved_tables = [str(t) for t in table_names if t]
        elif "table_name" in kwargs and kwargs["table_name"]:
            resolved_tables = [str(kwargs["table_name"])]

        if resolved_tables and self.engine:
            target_schema = get_session_schema_or_public(session_id)
            try:
                with self.engine.connect() as conn:
                    apply_session_search_path(conn, session_id)
                    for t_name in resolved_tables:
                        clean_var = f"data_{self._clean_identifier(t_name)}"
                        df = pd.read_sql(text(f'SELECT * FROM "{t_name}"'), conn)
                        loaded_dfs[clean_var] = df
                        if "data" not in loaded_dfs:
                            loaded_dfs["data"] = df
                queries = [f'SELECT * FROM "{t}"' for t in resolved_tables]
                executed_sql = ";\n".join(queries) + ";"
            except Exception as ex:
                logger.warning(f"Failed to load table(s) {resolved_tables} from schema '{target_schema}': {ex}")

        # 2. If not resolved by table_name, try given_path
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

        # 3. If still empty, query base tables present in the target schema (session or public)
        if not loaded_dfs and self.engine:
            target_schema = get_session_schema_or_public(session_id)
            try:
                with self.engine.connect() as conn:
                    apply_session_search_path(conn, session_id)
                    schema_tables = [
                        r[0]
                        for r in conn.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema = :s AND table_type = 'BASE TABLE' "
                                "ORDER BY table_name ASC"
                            ),
                            {"s": target_schema},
                        ).fetchall()
                    ]
                    for t_name in schema_tables:
                        clean_var = f"data_{self._clean_identifier(t_name)}"
                        df = pd.read_sql(text(f'SELECT * FROM "{t_name}"'), conn)
                        loaded_dfs[clean_var] = df
                        if "data" not in loaded_dfs:
                            loaded_dfs["data"] = df
                    if schema_tables:
                        queries = [f'SELECT * FROM "{t}"' for t in schema_tables]
                        executed_sql = ";\n".join(queries) + ";"
            except Exception as ex:
                logger.debug(f"Could not load tables from schema '{target_schema}': {ex}")

        actual_ids: List[int] = list(given_ids) if given_ids else ([] if given_id is None else [given_id])
        return loaded_dfs, given_id, actual_ids, executed_sql

    async def _prepare_dataset_node(self, state: MLAgentState) -> Dict[str, Any]:
        """Loads schema, feature types, and data preview for in-memory datasets."""
        trace = _current_ml_trace.get()
        given_path = state.get("dataset_path", "")
        given_id = state.get("dataset_id")
        given_ids = state.get("dataset_ids")
        table_names = state.get("table_names")
        sess_id = state.get("session_id")

        with trace_span(
            "ml_agent.prepare_dataset",
            parent=trace,
            input_data={
                "dataset_id": given_id,
                "dataset_ids": given_ids,
                "table_names": table_names,
                "session_id": sess_id,
            },
            metadata={"session_id": sess_id},
        ) as prep_span:
            loaded_dfs, matched_id, all_ids, executed_sql = self._resolve_in_memory_datasets(
                given_path=given_path,
                given_id=given_id,
                given_ids=given_ids,
                table_names=table_names,
                session_id=sess_id,
            )

            if not loaded_dfs:
                loaded_dfs = {"data": pd.DataFrame()}

            # Distinguish unique DataFrames by object identity
            unique_dfs: List[Tuple[str, pd.DataFrame]] = []
            seen_ids = set()
            for k, v in loaded_dfs.items():
                df_id = id(v)
                if df_id not in seen_ids:
                    seen_ids.add(df_id)
                    unique_dfs.append((k, v))

            is_multi = len(unique_dfs) > 1
            preview_sections: List[str] = []
            copy_stmts: List[str] = []

            if not is_multi:
                _, df = unique_dfs[0]
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

                loaded_dfs["data"] = unique_dfs[0][1]

            prep_span.update(
                output={
                    "datasets_loaded": list(loaded_dfs.keys()),
                    "is_multi_dataset": is_multi,
                    "dataset_id": matched_id,
                },
                metadata={
                    "dataset_id": matched_id,
                    "dataset_ids": all_ids,
                },
            )

            return {
                "in_memory_datasets": loaded_dfs,
                "dataset_id": matched_id,
                "dataset_ids": all_ids,
                "is_multi_dataset": is_multi,
                "copy_instructions": "\n".join(copy_stmts),
                "dataset_preview": "\n".join(preview_sections),
                "resolved_path": "",
                "sql_query": state.get("sql_query") or executed_sql or "",
            }

    async def _check_clarity_node(self, state: MLAgentState) -> Dict[str, Any]:
        """Evaluates if the user's task description is clear enough to proceed or if clarification is required."""
        trace = _current_ml_trace.get()
        task_desc = state.get("task_description", "")
        dataset_preview = state.get("dataset_preview", "")

        with trace_span(
            "ml_agent.check_clarity",
            parent=trace,
            input_data={
                "task_description": task_desc,
            },
            metadata={"session_id": state.get("session_id")},
        ) as clarity_span:
            handler = clarity_span.get_langchain_handler()
            config = {"callbacks": [handler]} if handler else {}

            prompt = prompt_loader.render(
                "task_clarity",
                task_description=task_desc,
                dataset_preview=dataset_preview,
            )

            needs_clarification = False
            questions: List[Dict[str, Any]] = []

            try:
                structured_model = self.chat_model.with_structured_output(TaskClarityOutput)
                result = await structured_model.ainvoke([HumanMessage(content=prompt)], config=config)
                if isinstance(result, dict):
                    result = TaskClarityOutput.model_validate(result)

                if isinstance(result, TaskClarityOutput):
                    needs_clarification = result.needs_clarification
                    questions = [q.model_dump() for q in result.questions]
            except Exception as ex:
                logger.warning(f"Structured clarity check failed ({ex}), falling back to standard invoke")
                try:
                    resp = await self.chat_model.ainvoke([HumanMessage(content=prompt)], config=config)
                    text_content = extract_text_from_message_content(resp.content).strip()
                    if "{" in text_content and "}" in text_content:
                        json_str = text_content[text_content.find("{") : text_content.rfind("}") + 1]
                    else:
                        json_str = text_content
                    data = json.loads(json_str)
                    needs_clarification = bool(data.get("needs_clarification", False))
                    questions = data.get("questions", [])
                except Exception as fb_err:
                    logger.error(f"Fallback clarity check failed: {fb_err}")

            if needs_clarification and questions:
                # Clarification is reserved as a last resort when neither the data nor the approach can be inferred.
                in_memory_dfs = state.get("in_memory_datasets", {})
                has_usable_data = any(
                    isinstance(df, pd.DataFrame) and not df.empty and len(df.columns) > 0
                    for df in in_memory_dfs.values()
                )

                task_lower = task_desc.lower()
                approach_keywords = [
                    "regress", "classif", "predict", "train", "model", "cluster",
                    "segment", "forecast", "detect", "score", "churn", "spend",
                    "price", "sales", "revenue", "order", "distribut", "correlat",
                    "trend", "scatter", "pca", "anomaly", "rfm", "customer",
                ]
                has_clear_approach = any(kw in task_lower for kw in approach_keywords)
                has_recommendations = any(bool(q.get("recommended")) for q in questions)

                # When data is usable or the approach is specified, auto-adopt recommended settings and proceed.
                if (has_usable_data or has_clear_approach) and (has_clear_approach or has_recommendations):
                    rec_instructions = [
                        f"{q.get('question', '')} -> Use recommended: {q.get('recommended')}"
                        for q in questions if q.get("recommended")
                    ]
                    alt_options = []
                    for q in questions:
                        rec = q.get("recommended")
                        opts = [o for o in q.get("options", []) if o != rec]
                        if opts:
                            alt_options.extend(opts)

                    config_notes = []
                    if rec_instructions:
                        config_notes.append(f"Auto-selected configuration: {'; '.join(rec_instructions)}")
                    if alt_options:
                        config_notes.append(f"Other available candidate variables: {', '.join(alt_options)}")

                    updated_task_desc = task_desc
                    if config_notes:
                        updated_task_desc = f"{task_desc}\n\n[{' | '.join(config_notes)}]"
                        logger.info(f"Auto-adopting ML configuration instead of clarifying: {config_notes}")

                    clarity_span.update(
                        output={"needs_clarification": False, "auto_adopted": True},
                    )
                    return {
                        "needs_clarification": False,
                        "clarification_questions": [],
                        "task_description": updated_task_desc,
                    }

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
                clarity_span.update(
                    output={"needs_clarification": True, "questions": questions},
                )
                return {
                    "needs_clarification": True,
                    "clarification_questions": questions,
                    "response": formatted_resp,
                }

            clarity_span.update(
                output={"needs_clarification": False},
            )
            return {
                "needs_clarification": False,
                "clarification_questions": [],
            }

    def _route_after_clarity(self, state: MLAgentState) -> Literal["clarify", "proceed"]:
        """Routes to END if user clarification is required, otherwise proceeds to code generation."""
        if state.get("needs_clarification"):
            return "clarify"
        return "proceed"

    async def _generate_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """Generates Python machine learning code and a concise title tailored to the user's task."""
        trace = _current_ml_trace.get()
        task_desc = state.get("task_description", "")
        with trace_span(
            "ml_agent.generate_code",
            parent=trace,
            input_data={
                "task_description": task_desc,
                "is_multi_dataset": state.get("is_multi_dataset", False),
            },
            metadata={
                "is_multi_dataset": state.get("is_multi_dataset", False),
            },
        ) as gen_span:
            handler = gen_span.get_langchain_handler()
            config = {"callbacks": [handler]} if handler else {}

            chart_guidelines = prompt_loader.render("chart_guidelines")
            prompt = prompt_loader.render(
                "code_generation",
                task_description=task_desc,
                dataset_preview=state.get("dataset_preview", ""),
                is_multi_dataset=state.get("is_multi_dataset", False),
                copy_instructions=state.get("copy_instructions", "df = data.copy()"),
                chart_guidelines=chart_guidelines,
            )

            messages = [
                HumanMessage(content=prompt),
            ]

            code = ""
            code_title = ""
            try:
                structured_model = self.chat_model.with_structured_output(MLCodeGenerationOutput)
                result = await structured_model.ainvoke(messages, config=config)
                if isinstance(result, dict):
                    result = MLCodeGenerationOutput.model_validate(result)

                if isinstance(result, MLCodeGenerationOutput):
                    code = self._extract_python_code(result.code)
                    code_title = truncate_words(result.code_title.strip(), max_words=5)
            except Exception as ex:
                logger.warning(f"Structured ML code generation failed ({ex}), falling back to direct invoke")

            if not code:
                resp = await self.chat_model.ainvoke(messages, config=config)
                content = extract_text_from_message_content(resp.content)
                code = self._extract_python_code(content)

            if not code_title:
                task_words = "".join(c for c in task_desc if c.isalnum() or c.isspace()).split()
                code_title = truncate_words(
                    " ".join(task_words[:5]).title() if task_words else "Machine Learning Script",
                    max_words=5,
                )
            else:
                code_title = truncate_words(code_title, max_words=5)

            clean_code = code.strip()

            gen_span.update(
                output={
                    "code_title": code_title,
                    "code_length": len(clean_code),
                    "code_preview": clean_code[:200],
                },
                metadata={
                    "code_title": code_title,
                },
            )

            return {
                "current_code": clean_code,
                "code_title": code_title,
            }

    async def _execute_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """Executes current Python code in the isolated subprocess runner with in-memory datasets."""
        trace = _current_ml_trace.get()
        code = state.get("current_code", "")
        in_memory_dfs = state.get("in_memory_datasets", {})

        with trace_span(
            "ml_agent.execute_code",
            parent=trace,
            input_data={
                "code_length": len(code),
                "in_memory_datasets": list(in_memory_dfs.keys()),
            },
            metadata={
                "code_title": state.get("code_title", ""),
            },
        ) as exec_span:
            res = await self.runner.run_code(code, in_memory_datasets=in_memory_dfs)
            success = res.get("success", False)

            if not success:
                exec_span.update(
                    level="WARNING",
                    status_message=res.get("error_trace", "")[:300] or "Execution encountered an error",
                    output={
                        "success": False,
                        "error_trace": res.get("error_trace", "")[:500],
                    },
                )
            else:
                exec_span.update(
                    output={
                        "success": True,
                        "stdout_length": len(res.get("stdout", "")),
                        "charts_count": len(res.get("charts", [])),
                    },
                )

            return {
                "execution_result": res,
                "error_trace": res.get("error_trace", ""),
                "success": success,
                "current_code": res.get("code", code),
            }

    def _route_after_execution(self, state: MLAgentState) -> Literal["repair", "summarize"]:
        """Routes to the self-healing repair node if execution failed and retries remain, otherwise summarizes."""
        if not state.get("success") and state.get("retry_count", 0) < self.max_retries:
            return "repair"
        return "summarize"

    async def _repair_code_node(self, state: MLAgentState) -> Dict[str, Any]:
        """Debugs and repairs Python code based on the execution traceback."""
        trace = _current_ml_trace.get()
        current_retries = state.get("retry_count", 0) + 1
        logger.info(f"MLAgent self-healing repair attempt {current_retries}/{self.max_retries}")

        with trace_span(
            "ml_agent.code_repair",
            parent=trace,
            input_data={
                "attempt": current_retries,
                "retry_count": current_retries,
                "error_trace": state.get("error_trace", "")[:500],
            },
            metadata={
                "attempt": current_retries,
                "retry_count": current_retries,
            },
        ) as rep_span:
            handler = rep_span.get_langchain_handler()
            config = {"callbacks": [handler]} if handler else {}

            chart_guidelines = prompt_loader.render("chart_guidelines")
            prompt = prompt_loader.render(
                "code_repair",
                task_description=state.get("task_description", ""),
                dataset_preview=state.get("dataset_preview", ""),
                current_code=state.get("current_code", ""),
                error_trace=state.get("error_trace", ""),
                is_multi_dataset=state.get("is_multi_dataset", False),
                copy_instructions=state.get("copy_instructions", "df = data.copy()"),
                chart_guidelines=chart_guidelines,
            )

            messages = [
                HumanMessage(content=prompt),
            ]
            resp = await self.chat_model.ainvoke(messages, config=config)
            content = extract_text_from_message_content(resp.content)
            fixed_code = self._extract_python_code(content)
            clean_fixed_code = fixed_code.strip()

            rep_span.update(
                output={
                    "repaired_code_length": len(clean_fixed_code),
                },
            )

            return {
                "current_code": clean_fixed_code,
                "retry_count": current_retries,
                "code_title": state.get("code_title", ""),
            }

    async def _summarize_results_node(self, state: MLAgentState) -> Dict[str, Any]:
        """Synthesizes the final analytical summary from console output and generated Plotly charts."""
        trace = _current_ml_trace.get()
        exec_res = state.get("execution_result", {})
        stdout = exec_res.get("stdout", "")
        charts = exec_res.get("charts", [])
        plots = exec_res.get("plots", [])
        success = state.get("success", False)

        with trace_span(
            "ml_agent.summarize_results",
            parent=trace,
            input_data={
                "success": success,
                "charts_count": len(charts),
            },
            metadata={
                "success": success,
            },
        ) as sum_span:
            if not success:
                error_summary = (
                    f"### Machine Learning Execution Failed\n\n"
                    f"The generated code could not execute successfully after {state.get('retry_count', 0)} attempts.\n\n"
                    f"**Error Details:**\n```\n{state.get('error_trace', '')}\n```"
                )
                sum_span.update(
                    level="ERROR",
                    output={"error_summary": error_summary},
                )
                return {"response": error_summary}

            task_desc = state.get("task_description", "")
            prompt = prompt_loader.render(
                "summary",
                task_description=task_desc,
                stdout=stdout,
                charts=charts,
                plots=plots,
            )

            messages = [
                HumanMessage(content=prompt),
            ]

            handler = sum_span.get_langchain_handler()
            config = {"callbacks": [handler]} if handler else {}

            resp = await self.chat_model.ainvoke(messages, config=config)
            summary_text = extract_text_from_message_content(resp.content)

            sum_span.update(
                output={"response": summary_text},
            )

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
        Persists generated Plotly chart JSON specifications into internal.generated_charts.

        Args:
            charts (List[Dict[str, Any]]): List of chart objects containing file_name and spec.
            dataset_id (Optional[int]): Optional associated dataset ID.
            session_id (Optional[str]): Active session ID.

        Returns:
            List[int]: Primary key IDs of the saved chart records.
        """
        if not self.engine or not charts:
            return []

        chart_ids: List[int] = []
        for ch in charts:
            spec = ch.get("spec", {})
            title = ""
            if isinstance(spec, dict):
                layout = spec.get("layout", {})
                layout_title = layout.get("title")
                if isinstance(layout_title, dict):
                    title = layout_title.get("text", "")
                elif isinstance(layout_title, str):
                    title = layout_title

                _clean_chart_spec(spec)

            if title:
                title = truncate_words(title, max_words=5)

            if not title:
                raw_title = ch.get("file_name", "Plotly Chart").replace(".json", "").replace("_", " ")
                clean_tokens = [
                    t
                    for t in raw_title.split()
                    if not (t.isdigit() or len(t) >= 6 and t.isalnum() and any(c.isdigit() for c in t))
                ]
                clean_title = " ".join(clean_tokens) if clean_tokens else raw_title
                title = truncate_words(clean_title.title() if clean_title else "Plotly Chart", max_words=5)

            chart_type = "plotly"
            if isinstance(spec, dict) and "data" in spec and isinstance(spec["data"], list) and len(spec["data"]) > 0:
                first_trace = spec["data"][0]
                if isinstance(first_trace, dict):
                    chart_type = first_trace.get("type", "plotly")

            try:
                with self.engine.begin() as conn:
                    res = conn.execute(
                        text("""
                            INSERT INTO internal.generated_charts (title, chart_type, spec, dataset_id, session_id)
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
        Persists generated ML Python code into internal.generated_scripts.

        Args:
            script (str): Executed Python code string.
            task_description (str): Short descriptive title for the script.
            dataset_id (Optional[int]): Optional associated dataset ID.
            session_id (Optional[str]): Active session ID.

        Returns:
            Optional[int]: Primary key ID of the saved script record, or None on failure.
        """
        if not self.engine or not script.strip():
            return None

        try:
            with self.engine.begin() as conn:
                res = conn.execute(
                    text("""
                        INSERT INTO internal.generated_scripts (script, language, task_description, dataset_id, session_id)
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

    async def run(
        self,
        task_description: str,
        dataset_path: Optional[str] = None,
        dataset_id: Optional[int] = None,
        dataset_ids: Optional[List[int]] = None,
        table_names: Optional[Any] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Runs the full end-to-end ML Agent workflow asynchronously, returning the analytical response
        and ID-only metadata.

        Args:
            task_description (str): Natural language task requirement.
            dataset_path (Optional[str]): Optional path to CSV or Excel dataset file.
            dataset_id (Optional[int]): Optional database identifier of the primary dataset.
            dataset_ids (Optional[List[int]]): Optional list of multiple dataset identifiers.
            table_names (Optional[Any]): Relational database table name or list of table names.
            session_id (Optional[str]): Optional session ID to bind and scope the analysis.
            trace_id (Optional[str]): Distributed trace ID to bind execution.
            parent_observation_id (Optional[str]): Parent observation ID within the trace.
            **kwargs (Any): Additional keyword arguments (such as sql_query or table_name).

        Returns:
            Dict[str, Any]: Structured dictionary with response text and ID-only metadata.
        """
        resolved_tables: Optional[List[str]] = None
        if isinstance(table_names, str):
            resolved_tables = [table_names]
        elif isinstance(table_names, list):
            resolved_tables = [str(t) for t in table_names if t]
        elif "table_name" in kwargs and kwargs["table_name"]:
            resolved_tables = [str(kwargs["table_name"])]

        initial_state: MLAgentState = {
            "task_description": task_description,
            "dataset_path": dataset_path or "",
            "dataset_id": dataset_id,
            "dataset_ids": dataset_ids,
            "table_names": resolved_tables,
            "session_id": session_id,
            "sql_query": kwargs.get("sql_query") or "",
            "in_memory_datasets": {},
            "is_multi_dataset": False,
            "copy_instructions": "df = data.copy()",
            "resolved_path": "",
            "dataset_preview": "",
            "current_code": "",
            "code_title": "",
            "execution_result": {},
            "error_trace": "",
            "retry_count": 0,
            "response": "",
            "success": False,
            "needs_clarification": False,
            "clarification_questions": [],
        }

        if trace_id:
            parent_scope = trace_span(
                name="ml_agent.run_ml_analysis",
                trace_id=trace_id,
                parent_observation_id=parent_observation_id,
                input_data={
                    "task_description": task_description,
                    "dataset_id": dataset_id,
                    "dataset_ids": dataset_ids,
                    "table_names": resolved_tables,
                    "session_id": session_id,
                },
                metadata={
                    "session_id": session_id,
                    "dataset_id": dataset_id,
                },
            )
            span_or_trace = parent_scope.__enter__()
        else:
            parent_scope = None
            span_or_trace = create_trace(
                name="ml_agent.run_ml_analysis",
                session_id=session_id,
                input_data={
                    "task_description": task_description,
                    "dataset_id": dataset_id,
                    "dataset_ids": dataset_ids,
                    "table_names": resolved_tables,
                    "session_id": session_id,
                },
                metadata={
                    "session_id": session_id,
                    "dataset_id": dataset_id,
                },
                tags=["ml_agent"],
            )

        trace_token = _current_ml_trace.set(span_or_trace)

        try:
            final_state = await self.graph.ainvoke(initial_state)

            if final_state.get("needs_clarification"):
                clarif_meta = build_domain_metadata(
                    status="clarification_needed",
                    questions=final_state.get("clarification_questions", []),
                    dataset_id=final_state.get("dataset_id"),
                    dataset_ids=final_state.get("dataset_ids"),
                )
                span_or_trace.update(
                    output={"response": final_state.get("response", ""), "clarification_needed": True},
                    metadata={"final_metadata": clarif_meta},
                )
                flush_langfuse()
                return {
                    "response": final_state.get("response", ""),
                    "metadata": clarif_meta,
                }

            exec_res = final_state.get("execution_result") or {}
            resolved_dataset_id = final_state.get("dataset_id")
            resolved_dataset_ids = final_state.get("dataset_ids")
            resolved_sess_id = final_state.get("session_id")

            charts = exec_res.get("charts", [])
            chart_ids = self._save_charts_to_db(charts, dataset_id=resolved_dataset_id, session_id=resolved_sess_id)

            code_script = final_state.get("current_code", "")
            code_title = final_state.get("code_title")
            if not code_title:
                task_words = "".join(c for c in task_description if c.isalnum() or c.isspace()).split()
                code_title = truncate_words(
                    " ".join(task_words[:5]).title() if task_words else "Machine Learning Script",
                    max_words=5,
                )
            else:
                code_title = truncate_words(code_title, max_words=5)

            script_id = self._save_script_to_db(
                code_script,
                task_description=code_title,
                dataset_id=resolved_dataset_id,
                session_id=resolved_sess_id,
            )

            metadata = build_domain_metadata(
                chart_ids=chart_ids,
                script_id=script_id,
                python_script_id=script_id,
                dataset_id=resolved_dataset_id,
                dataset_ids=resolved_dataset_ids,
                table_names=final_state.get("table_names"),
                code=code_script,
                code_title=code_title,
                task_description=code_title,
                sql_query=final_state.get("sql_query") or kwargs.get("sql_query") or None,
            )

            span_or_trace.update(
                output={"response": final_state.get("response", "")},
                metadata={"final_metadata": metadata},
            )
            flush_langfuse()

            return {
                "response": final_state.get("response", ""),
                "metadata": metadata,
            }
        finally:
            _current_ml_trace.reset(trace_token)
            if parent_scope is not None:
                parent_scope.__exit__(None, None, None)

    def run_sync(
        self,
        task_description: str,
        dataset_path: Optional[str] = None,
        dataset_id: Optional[int] = None,
        dataset_ids: Optional[List[int]] = None,
        table_names: Optional[Any] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Synchronous execution wrapper around run().

        Args:
            task_description (str): Natural language task requirement.
            dataset_path (Optional[str]): Optional path to CSV dataset file.
            dataset_id (Optional[int]): Optional database identifier of the dataset.
            dataset_ids (Optional[List[int]]): Optional list of multiple dataset identifiers.
            table_names (Optional[Any]): Relational database table name or list of table names.
            session_id (Optional[str]): Optional session ID to bind and scope the analysis.
            **kwargs (Any): Additional keyword arguments passed to run().

        Returns:
            Dict[str, Any]: Structured dictionary with response text and ID-only metadata.
        """
        coro = self.run(
            task_description=task_description,
            dataset_path=dataset_path,
            dataset_id=dataset_id,
            dataset_ids=dataset_ids,
            table_names=table_names,
            session_id=session_id,
            **kwargs,
        )
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)


def create_ml_agent(settings: Optional[MLAgentSettings] = None, engine: Optional[Engine] = None) -> MLAgent:
    """Constructs and configures a fully functional MLAgent instance."""
    cfg = settings or get_ml_settings()
    python_bin = cfg.resolve_python_executable()

    runner = MLCodeRunner(
        python_bin=python_bin,
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
        max_retries=cfg.max_retries,
        engine=db_engine,
    )


build_ml_agent = create_ml_agent
