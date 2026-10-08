import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from nicegui import app, run, ui

warnings.filterwarnings("ignore", category=UserWarning)

import httpx

# AI Service endpoint configuration
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")

# Configure static output directory to allow direct CSV downloads
OUTPUT_DIR = Path("./output").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.add_static_files("/output", str(OUTPUT_DIR))


class DBStudioUI:
    def __init__(self) -> None:
        self.ai_service_url: str = AI_SERVICE_URL.rstrip("/")
        self.current_csv_path: Optional[str] = None
        self.current_csv_name: Optional[str] = None
        self.is_busy: bool = False

    async def send_query(self, query_text: str) -> Dict[str, Any]:
        """
        Sends natural language query to the AI service endpoint.

        Args:
            query_text (str): User request.

        Returns:
            Dict[str, Any]: Response from the AI service.
        """
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{self.ai_service_url}/api/query",
                json={"query": query_text},
            )
            resp.raise_for_status()
            return resp.json()

    def load_table_from_metadata(self, table_meta: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Loads columns and rows for ui.table from CSV file or metadata preview.

        Args:
            table_meta (Dict[str, Any]): Table metadata from agent output.

        Returns:
            tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: Formatted columns and rows for ui.table.
        """
        file_name = table_meta.get("file_name", "")
        file_path_str = table_meta.get("file_path", "")

        candidate_paths = []
        if file_name:
            candidate_paths.append(OUTPUT_DIR / file_name)
        if file_path_str:
            candidate_paths.append(Path(file_path_str))
            candidate_paths.append(OUTPUT_DIR / Path(file_path_str).name)

        target_file = None
        for p in candidate_paths:
            if p.exists() and p.is_file():
                target_file = p
                break

        if target_file:
            try:
                df = pd.read_csv(target_file)
                columns = [
                    {"name": col, "label": col, "field": col, "sortable": True, "align": "left"}
                    for col in df.columns
                ]
                rows = df.fillna("").to_dict(orient="records")
                self.current_csv_path = str(target_file)
                self.current_csv_name = target_file.name
                return columns, rows
            except Exception as e:
                print(f"Error reading CSV {target_file}: {e}")

        # Fallback to metadata preview
        cols = table_meta.get("columns", [])
        preview = table_meta.get("preview", [])
        columns = [
            {"name": col, "label": col, "field": col, "sortable": True, "align": "left"}
            for col in cols
        ]
        rows = [dict(zip(cols, r)) for r in preview]
        self.current_csv_name = file_name or "preview_data.csv"
        return columns, rows


def create_ui() -> None:
    """
    Constructs the NiceGUI layout featuring chat on the left and interactive table widget on the right.

    Args:
        None

    Returns:
        None
    """
    studio = DBStudioUI()

    # Enable dark mode by default
    dark = ui.dark_mode(value=True)

    # Top Navigation Header
    with ui.header().classes("w-full bg-slate-900 border-b border-slate-800 px-6 py-3 flex items-center justify-between shadow-md"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("hub", size="2rem").classes("text-indigo-400")
            with ui.column().classes("gap-0"):
                ui.label("Multi-Agent Orchestrator Studio").classes("text-lg font-bold text-slate-100 tracking-wide")
                ui.label("Planner → MCP Executor (db_agent) → Finalizer").classes("text-xs text-slate-400")

        with ui.row().classes("items-center gap-3"):
            ui.badge(f"AI Backend: {studio.ai_service_url}", color="slate-800").props("outline").classes("text-xs text-indigo-300 font-mono")

            ui.button(
                icon="dark_mode",
                on_click=lambda: dark.toggle(),
            ).props("flat round dense color=white").tooltip("Toggle dark/light mode")

    # Main Split Workspace
    with ui.element("main").classes("w-full px-6 py-4 grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-80px)]"):

        # ==========================================
        # LEFT COLUMN: CHAT INTERFACE (5 cols)
        # ==========================================
        with ui.card().classes("lg:col-span-5 flex flex-col h-full bg-slate-900/60 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg"):
            # Chat Header
            with ui.row().classes("w-full px-5 py-3 border-b border-slate-800 items-center justify-between bg-slate-900/90"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("chat", size="1.2rem").classes("text-indigo-400")
                    ui.label("Agent Conversation").classes("font-semibold text-slate-200 text-sm")
                ui.badge("MCP Client Orchestrator", color="indigo-950").classes("text-indigo-300 text-xs")

            # Chat Messages Scroll Area
            chat_scroll = ui.scroll_area().classes("flex-1 p-5 space-y-4 overflow-y-auto")
            with chat_scroll:
                messages_container = ui.column().classes("w-full gap-4")

                # Welcome initial message
                with messages_container:
                    with ui.card().classes("w-full bg-slate-800/70 border border-slate-700/60 rounded-lg p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.avatar("hub", color="indigo-600", text_color="white", size="sm")
                            ui.label("Orchestrator").classes("font-semibold text-xs text-indigo-300")
                            ui.label("System").classes("text-[10px] text-slate-400")
                        ui.markdown(
                            "Hello! I am your **Multi-Agent Orchestrator** (MCP Client). "
                            "When you ask a question, the **Planner** determines the sequence of tools to call, "
                            "the **Executor** runs them via MCP on connected agents (like **DB Agent**), "
                            "and the **Finalizer** synthesizes the final answer and table results."
                        ).classes("text-sm text-slate-200 leading-relaxed")

            # Quick Query Chips
            with ui.column().classes("w-full px-4 pt-2 pb-1 border-t border-slate-800/80 bg-slate-900/40"):
                ui.label("Suggested Queries:").classes("text-[11px] font-medium text-slate-400")
                with ui.row().classes("gap-1.5 flex-wrap"):
                    async def set_and_send(prompt: str) -> None:
                        query_input.value = prompt
                        await handle_submit()

                    for prompt_text in [
                        "Find top 3 customers by total order amount",
                        "Show all products with price and stock",
                        "Calculate total sales by product category",
                    ]:
                        ui.chip(
                            prompt_text,
                            on_click=lambda p=prompt_text: set_and_send(p),
                        ).props("dense clickable outline color=indigo-400").classes("text-[11px]")

            # Chat Input Form
            with ui.row().classes("w-full p-4 border-t border-slate-800 bg-slate-900/90 items-center gap-2"):
                query_input = ui.input(
                    placeholder="Ask database query... (Press Enter to send)",
                ).props("outlined dense rounded autogrow clearable").classes("flex-1 text-sm bg-slate-800/50 text-white")

                send_button = ui.button(icon="send").props("rounded unelevated color=indigo-600")

        # ==========================================
        # RIGHT COLUMN: TABLE WIDGET (7 cols)
        # ==========================================
        with ui.card().classes("lg:col-span-7 flex flex-col h-full bg-slate-900/60 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg"):
            # Table Header
            with ui.row().classes("w-full px-5 py-3 border-b border-slate-800 items-center justify-between bg-slate-900/90"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("table_chart", size="1.2rem").classes("text-emerald-400")
                    ui.label("Query Results Table").classes("font-semibold text-slate-200 text-sm")

                with ui.row().classes("items-center gap-2"):
                    rows_badge = ui.badge("0 rows", color="slate-800").classes("text-xs text-slate-300 font-mono")
                    cols_badge = ui.badge("0 columns", color="slate-800").classes("text-xs text-slate-300 font-mono")
                    file_badge = ui.badge("No file", color="slate-800").classes("text-xs text-slate-400 font-mono")

                    download_btn = ui.button(icon="download").props("flat round dense color=slate-400").tooltip("Download CSV")
                    download_btn.disable()

            # Search bar inside Table Widget
            with ui.row().classes("w-full px-5 py-2.5 border-b border-slate-800/60 bg-slate-900/30 items-center justify-between gap-4"):
                table_filter = ui.input(placeholder="Filter rows...").props("dense outlined rounded clearable").classes("w-64 text-xs")
                with ui.row().classes("items-center gap-2"):
                    ui.label("Pagination: 10 rows/page").classes("text-[11px] text-slate-500 font-mono")

            # Table Container
            table_container = ui.column().classes("flex-1 w-full p-4 overflow-auto justify-center items-center")

            with table_container:
                # Empty State
                empty_state = ui.column().classes("items-center justify-center py-16 text-center gap-3")
                with empty_state:
                    ui.icon("table_view", size="4rem").classes("text-slate-700")
                    ui.label("No Table Data Loaded").classes("text-base font-semibold text-slate-400")
                    ui.label("Execute a query in the chat to see results rendered in this table widget.").classes("text-xs text-slate-500 max-w-sm")

                # The actual ui.table component
                table_widget = ui.table(
                    columns=[],
                    rows=[],
                    row_key="id",
                    pagination={"rowsPerPage": 10},
                ).props("flat dense").classes("w-full flex-1 border border-slate-800 rounded-lg text-xs")
                table_widget.set_visibility(False)
                table_filter.bind_value_to(table_widget, "filter")

    # Download button handler
    def handle_download() -> None:
        if studio.current_csv_path and Path(studio.current_csv_path).exists():
            ui.download(f"/output/{Path(studio.current_csv_path).name}")
        else:
            ui.notify("No CSV file available to download", type="warning")

    download_btn.on_click(handle_download)

    # Query Submission Logic
    async def handle_submit() -> None:
        query_text = (query_input.value or "").strip()
        if not query_text or studio.is_busy:
            return

        studio.is_busy = True
        send_button.disable()
        query_input.value = ""

        # 1. Render User Message in Chat
        with messages_container:
            with ui.card().classes("w-full bg-indigo-950/40 border border-indigo-800/40 rounded-lg p-3 self-end"):
                with ui.row().classes("items-center gap-2 mb-1"):
                    ui.avatar("person", color="slate-700", text_color="white", size="xs")
                    ui.label("You").classes("font-semibold text-xs text-indigo-300")
                ui.label(query_text).classes("text-sm text-slate-100 font-medium")

        chat_scroll.scroll_to(percent=1.0)

        # 2. Render Temporary Thinking Message
        with messages_container:
            thinking_card = ui.card().classes("w-full bg-slate-800/50 border border-slate-700/40 rounded-lg p-3")
            with thinking_card:
                with ui.row().classes("items-center gap-3"):
                    ui.spinner("dots", size="sm", color="indigo-400")
                    ui.label("Planner formulating steps & calling MCP tools...").classes("text-xs text-slate-400 italic")

        chat_scroll.scroll_to(percent=1.0)

        try:
            # 3. Call AI Service Endpoint
            result = await studio.send_query(query_text)

            # Remove thinking indicator
            thinking_card.delete()

            response_text = result.get("response", "Query completed.")
            metadata = result.get("metadata") or {}
            table_meta = metadata.get("table") or {}
            code_meta = metadata.get("code") or {}
            sql_query = code_meta.get("query", "")
            plan = result.get("plan") or {}
            steps = plan.get("steps", []) if isinstance(plan, dict) else []
            thought = plan.get("thought", "") if isinstance(plan, dict) else ""

            # 4. Render Assistant Message with Plan, Tool Calls, Final Response, and SQL
            with messages_container:
                with ui.card().classes("w-full bg-slate-800/70 border border-slate-700/60 rounded-lg p-4 space-y-3"):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.row().classes("items-center gap-2"):
                            ui.avatar("hub", color="indigo-600", text_color="white", size="xs")
                            ui.label("Orchestrator").classes("font-semibold text-xs text-indigo-300")
                        if table_meta.get("file_name"):
                            ui.badge(f"Export: {table_meta['file_name']}", color="slate-900").classes("text-[10px] text-slate-400 font-mono")

                    # Display Planner Steps & MCP Tool Calling Trace
                    if steps:
                        with ui.expansion("Plan & MCP Execution Trace", icon="account_tree").props("dense default-opened=false").classes("w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"):
                            if thought:
                                ui.label(f"Strategy: {thought}").classes("text-[11px] text-slate-400 mb-2 italic")
                            for s in steps:
                                with ui.row().classes("items-center gap-2 my-1"):
                                    step_id = s.get("step_id", "")
                                    tool_name = s.get("tool_name", "")
                                    desc = s.get("description", "")
                                    ui.badge(f"Step {step_id}", color="indigo-900").classes("text-[10px] text-indigo-200")
                                    ui.label(f"{tool_name}").classes("font-mono text-xs text-emerald-400")
                                    if desc:
                                        ui.label(f"({desc})").classes("text-[11px] text-slate-400")

                    # Finalizer Synthesized Response
                    ui.markdown(response_text).classes("text-sm text-slate-200 leading-relaxed")

                    if sql_query:
                        with ui.expansion("Generated SQL Statement", icon="code").props("dense default-opened=false").classes("w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"):
                            ui.code(sql_query, language="sql").classes("w-full text-xs")

            chat_scroll.scroll_to(percent=1.0)

            # 5. Populate and Display the Table Widget
            columns, rows = studio.load_table_from_metadata(table_meta)
            if columns and rows:
                table_widget.columns = columns
                table_widget.rows = rows
                table_widget.row_key = columns[0]["name"] if columns else "id"
                table_widget.update()

                empty_state.set_visibility(False)
                table_widget.set_visibility(True)

                rows_badge.text = f"{len(rows)} rows"
                cols_badge.text = f"{len(columns)} cols"
                file_badge.text = studio.current_csv_name or "Exported CSV"
                download_btn.enable()

                ui.notify(f"Table updated: {len(rows)} rows loaded", type="positive", position="top-right")
            else:
                empty_state.set_visibility(True)
                table_widget.set_visibility(False)
                rows_badge.text = "0 rows"
                cols_badge.text = "0 cols"
                file_badge.text = "Empty result"
                download_btn.disable()

        except Exception as error:
            thinking_card.delete()
            with messages_container:
                with ui.card().classes("w-full bg-rose-950/40 border border-rose-800/50 rounded-lg p-3"):
                    with ui.row().classes("items-center gap-2 mb-1"):
                        ui.icon("error", color="rose-400", size="sm")
                        ui.label("Execution Error").classes("font-semibold text-xs text-rose-300")
                    ui.label(str(error)).classes("text-xs text-rose-200 font-mono")

            chat_scroll.scroll_to(percent=1.0)
            ui.notify(f"Error executing query: {error}", type="negative", position="top-right")

        finally:
            studio.is_busy = False
            send_button.enable()

    send_button.on_click(handle_submit)
    query_input.on("keydown.enter", handle_submit)


def main() -> None:
    """
    Main entry point for starting the NiceGUI web server.

    Args:
        None

    Returns:
        None
    """
    create_ui()
    ui.run(
        title="Database Agent Studio",
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
