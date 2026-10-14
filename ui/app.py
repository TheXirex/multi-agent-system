from datetime import datetime
import json
import os
from typing import Any, Dict, List, Optional
import warnings

import httpx
from nicegui import ui
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

# AI Service endpoint configuration
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")


class DBStudioUI:
    def __init__(self) -> None:
        self.ai_service_url: str = AI_SERVICE_URL.rstrip("/")
        self.current_session_id: Optional[str] = None
        self.current_session_title: str = "New Session"
        self.current_dataset_rows: List[Dict[str, Any]] = []
        self.current_dataset_columns: List[str] = []
        self.current_csv_name: Optional[str] = None
        self.is_busy: bool = False

    async def fetch_sessions(self) -> List[Dict[str, Any]]:
        """
        Retrieves all chat sessions from PostgreSQL backend.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.ai_service_url}/api/sessions")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            print(f"Error fetching sessions: {ex}")
        return []

    async def create_session(self, title: str = "New Session") -> Optional[Dict[str, Any]]:
        """
        Creates a new chat session in the database.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.ai_service_url}/api/sessions",
                    json={"title": title},
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            print(f"Error creating session: {ex}")
        return None

    async def get_session_detail(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves full details and message history of a chat session.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.ai_service_url}/api/sessions/{session_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            print(f"Error fetching session detail {session_id}: {ex}")
        return None

    async def delete_session(self, session_id: str) -> bool:
        """
        Deletes a chat session and its history from the database.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.delete(f"{self.ai_service_url}/api/sessions/{session_id}")
                return resp.status_code == 200
        except Exception as ex:
            print(f"Error deleting session {session_id}: {ex}")
        return False

    async def send_query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends natural language query to the AI service endpoint with session memory.
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.ai_service_url}/api/query",
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
                resp = await client.get(f"{self.ai_service_url}/api/datasets/{dataset_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            print(f"Error fetching dataset {dataset_id}: {ex}")
        return None

    async def fetch_chart(self, chart_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches Plotly chart JSON specification from backend by chart_id.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.ai_service_url}/api/charts/{chart_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            print(f"Error fetching chart {chart_id}: {ex}")
        return None

    async def fetch_script(self, script_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches script content from backend by script_id.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{self.ai_service_url}/api/scripts/{script_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as ex:
            print(f"Error fetching script {script_id}: {ex}")
        return None


def create_ui() -> None:
    """
    Constructs the NiceGUI layout featuring session management, chat with multi-turn memory,
    and tabbed workspace (Sessions, Table Data, Visualizations, Code & Scripts).
    """
    studio = DBStudioUI()

    # Enable dark mode
    ui.dark_mode(value=True)

    # Top Navigation Header
    with ui.header().classes("w-full bg-slate-900 border-b border-slate-800 px-6 py-3 flex items-center justify-between shadow-md"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("hub", size="1.8rem").classes("text-indigo-400")
            ui.label("Multi-Agent System").classes("text-lg font-bold text-slate-100 tracking-wide")
            active_session_badge = ui.badge("Session: None", color="slate-800").classes("text-xs text-indigo-300 font-mono px-2 py-1 border border-indigo-900/50")

        with ui.row().classes("items-center gap-2"):
            new_session_header_btn = ui.button("New Chat", icon="add").props("dense unelevated color=indigo-600").classes("text-xs font-semibold")

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
                    chat_title_label = ui.label("Conversation").classes("font-semibold text-slate-200 text-sm")

                with ui.row().classes("items-center gap-1"):
                    browse_sessions_btn = ui.button(icon="forum").props("flat round dense color=slate-400").tooltip("Browse All Sessions")
                    new_session_chat_btn = ui.button(icon="add").props("flat round dense color=indigo-400").tooltip("Start Fresh Session")

            # Chat Messages Scroll Area
            chat_scroll = ui.scroll_area().classes("flex-1 p-5 space-y-4 overflow-y-auto")
            with chat_scroll:
                messages_container = ui.column().classes("w-full gap-4")

            # Quick Query Chips
            with ui.column().classes("w-full px-4 pt-2 pb-1 border-t border-slate-800/80 bg-slate-900/40"):
                ui.label("Suggested Queries & Refinements:").classes("text-[11px] font-medium text-slate-400")
                with ui.row().classes("gap-1.5 flex-wrap"):
                    async def set_and_send(prompt: str) -> None:
                        query_input.value = prompt
                        await handle_submit()

                    for prompt_text in [
                        "Show table structures and summary distributions of available data",
                        "Extract the primary numerical and categorical attributes into a dataset",
                        "Train a regression model on primary numerical values and plot feature importances",
                        "Change the previous visualization into an interactive scatter plot with trendline",
                        "Cluster records into segments based on numerical features and plot the clusters",
                    ]:
                        ui.chip(
                            prompt_text,
                            on_click=lambda p=prompt_text: set_and_send(p),
                        ).props("dense clickable outline color=indigo-400").classes("text-[11px]")

            # Chat Input Form
            with ui.row().classes("w-full p-4 border-t border-slate-800 bg-slate-900/90 items-center gap-2"):
                query_input = ui.input(
                    placeholder="Ask data query, ML task, or follow-up question... (Enter to send)",
                ).props("outlined dense rounded autogrow clearable").classes("flex-1 text-sm bg-slate-800/50 text-white")

                send_button = ui.button(icon="send").props("rounded unelevated color=indigo-600")

        # ==========================================
        # RIGHT COLUMN: TABBED WORKSPACE (7 cols)
        # ==========================================
        with ui.card().classes("lg:col-span-7 flex flex-col h-full bg-slate-900/60 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg"):
            # Workspace Header with Navigation Tabs
            with ui.row().classes("w-full px-4 py-2 border-b border-slate-800 items-center justify-between bg-slate-900/90"):
                with ui.tabs().props("dense no-caps inline-label indicator-color=indigo-400 active-color=indigo-400 text-color=slate-400") as workspace_tabs:
                    tab_sessions = ui.tab("Sessions", icon="forum")
                    tab_table = ui.tab("Table Data", icon="table_chart")
                    tab_plots = ui.tab("Visualizations", icon="insights")
                    tab_code = ui.tab("Code & Scripts", icon="code")

                with ui.row().classes("items-center gap-2"):
                    sessions_count_badge = ui.badge("0 sessions", color="slate-800").classes("text-xs text-slate-300 font-mono")
                    rows_badge = ui.badge("0 rows", color="slate-800").classes("text-xs text-slate-300 font-mono")
                    plots_badge = ui.badge("0 charts", color="slate-800").classes("text-xs text-slate-300 font-mono")
                    download_btn = ui.button(icon="download").props("flat round dense color=slate-400").tooltip("Download CSV")
                    download_btn.disable()

            with ui.tab_panels(workspace_tabs, value=tab_sessions).classes("flex-1 w-full p-0 bg-transparent overflow-hidden"):
                # ---------------- TAB 0: SESSIONS ----------------
                with ui.tab_panel(tab_sessions).classes("p-4 flex flex-col h-full w-full overflow-y-auto gap-4"):
                    with ui.row().classes("w-full justify-between items-center pb-2 border-b border-slate-800/80"):
                        with ui.column().classes("gap-0"):
                            ui.label("Saved Chat Sessions").classes("text-sm font-bold text-slate-200")
                            ui.label("Browse, switch, or resume multi-turn conversations stored in PostgreSQL").classes("text-xs text-slate-500")
                        with ui.row().classes("items-center gap-2"):
                            refresh_sessions_btn = ui.button(icon="refresh").props("flat round dense color=slate-400").tooltip("Refresh Sessions")
                            create_new_session_btn = ui.button("+ New Session", icon="add").props("dense unelevated color=indigo-600").classes("text-xs font-semibold")

                    sessions_list_container = ui.column().classes("w-full gap-3")

                # ---------------- TAB 1: TABLE DATA ----------------
                with ui.tab_panel(tab_table).classes("p-0 flex flex-col h-full w-full"):
                    with ui.row().classes("w-full px-5 py-2.5 border-b border-slate-800/60 bg-slate-900/30 items-center justify-between gap-4"):
                        table_filter = ui.input(placeholder="Filter rows...").props("dense outlined rounded clearable").classes("w-64 text-xs")
                        with ui.row().classes("items-center gap-2"):
                            cols_badge = ui.badge("0 cols", color="slate-800").classes("text-[11px] text-slate-400 font-mono")
                            file_badge = ui.badge("No file", color="slate-800").classes("text-[11px] text-slate-400 font-mono")

                    table_container = ui.column().classes("flex-1 w-full p-4 overflow-auto justify-center items-center")
                    with table_container:
                        empty_state = ui.column().classes("items-center justify-center py-16 text-center gap-3")
                        with empty_state:
                            ui.icon("table_view", size="4rem").classes("text-slate-700")
                            ui.label("No Table Data Loaded").classes("text-base font-semibold text-slate-400")
                            ui.label("Execute a query in the chat to see results rendered in this table widget.").classes("text-xs text-slate-500 max-w-sm")

                        table_widget = ui.table(
                            columns=[],
                            rows=[],
                            row_key="id",
                            pagination={"rowsPerPage": 10},
                        ).props("flat dense").classes("w-full flex-1 border border-slate-800 rounded-lg text-xs")
                        table_widget.set_visibility(False)
                        table_filter.bind_value_to(table_widget, "filter")

                # ---------------- TAB 2: VISUALIZATIONS ----------------
                with ui.tab_panel(tab_plots).classes("p-4 flex flex-col h-full w-full overflow-y-auto"):
                    plots_container = ui.column().classes("w-full gap-6 items-center")
                    plots_empty = ui.column().classes("items-center justify-center py-16 text-center gap-3 w-full")
                    with plots_empty:
                        ui.icon("bar_chart", size="4rem").classes("text-slate-700")
                        ui.label("No Visualizations Generated").classes("text-base font-semibold text-slate-400")
                        ui.label("Ask the agent to plot or analyze data to view interactive Plotly charts here.").classes("text-xs text-slate-500 max-w-sm")

                # ---------------- TAB 3: CODE & SCRIPTS ----------------
                with ui.tab_panel(tab_code).classes("p-4 flex flex-col h-full w-full overflow-y-auto gap-4"):
                    code_container = ui.column().classes("w-full gap-4")
                    code_empty = ui.column().classes("items-center justify-center py-16 text-center gap-3 w-full")
                    with code_empty:
                        ui.icon("terminal", size="4rem").classes("text-slate-700")
                        ui.label("No Generated Code").classes("text-base font-semibold text-slate-400")
                        ui.label("Executed SQL queries and ML Python scripts will appear here.").classes("text-xs text-slate-500 max-w-sm")

    # Download CSV button handler
    def handle_download() -> None:
        if studio.current_dataset_rows:
            df = pd.DataFrame(studio.current_dataset_rows)
            csv_str = df.to_csv(index=False)
            filename = studio.current_csv_name or "dataset.csv"
            ui.download(csv_str.encode("utf-8"), filename=filename)
        else:
            ui.notify("No dataset available to download", type="warning")

    download_btn.on_click(handle_download)

    # -------------------------------------------------------------
    # Render Helpers: Chat Cards & Workspace Artifacts
    # -------------------------------------------------------------
    def render_user_message(text_content: str) -> None:
        with messages_container:
            with ui.card().classes("w-full bg-indigo-950/40 border border-indigo-800/40 rounded-lg p-3 self-end"):
                with ui.row().classes("items-center gap-2 mb-1"):
                    ui.avatar("person", color="slate-700", text_color="white", size="xs")
                    ui.label("You").classes("font-semibold text-xs text-indigo-300")
                ui.label(text_content).classes("text-sm text-slate-100 font-medium")

    async def render_assistant_message(
        response_text: str,
        metadata: Dict[str, Any],
        update_workspace: bool = True,
    ) -> None:
        dataset_id = metadata.get("dataset_id")
        chart_id = metadata.get("chart_id")
        chart_ids = metadata.get("chart_ids") or ([chart_id] if chart_id else [])
        script_id = metadata.get("script_id")

        dataset_data = await studio.fetch_dataset(dataset_id) if dataset_id else None
        charts_data = []
        for cid in chart_ids:
            c = await studio.fetch_chart(cid)
            if c:
                charts_data.append(c)
        script_data = await studio.fetch_script(script_id) if script_id else None

        sql_query = dataset_data.get("query", "") if dataset_data else ""
        python_script = script_data.get("script", "") if script_data else ""

        with messages_container:
            with ui.card().classes("w-full bg-slate-800/70 border border-slate-700/60 rounded-lg p-4 space-y-3"):
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.row().classes("items-center gap-2"):
                        ui.avatar("smart_toy", color="indigo-600", text_color="white", size="xs")
                        ui.label("Orchestrator").classes("font-semibold text-xs text-indigo-300")
                    with ui.row().classes("items-center gap-1.5"):
                        if dataset_data and dataset_data.get("file_name"):
                            ui.badge(f"Dataset #{dataset_id}: {dataset_data['file_name']}", color="slate-900").classes("text-[10px] text-slate-400 font-mono")
                        if charts_data:
                            ui.badge(f"{len(charts_data)} Plotly Chart{'s' if len(charts_data) > 1 else ''}", color="indigo-900").classes("text-[10px] text-indigo-300 font-mono")

                ui.markdown(response_text).classes("text-sm text-slate-200 leading-relaxed")

                # Inline Plotly charts preview
                if charts_data:
                    with ui.column().classes("w-full gap-3 pt-2"):
                        ui.label("Interactive Visualizations:").classes("text-xs font-semibold text-slate-300")
                        for ch in charts_data:
                            spec = ch.get("spec")
                            if spec:
                                with ui.card().classes("w-full bg-slate-900/90 border border-slate-700/60 p-3 rounded-lg overflow-hidden"):
                                    with ui.row().classes("w-full justify-between items-center mb-1"):
                                        ui.label(ch.get("title", "Interactive Plot")).classes("text-xs font-semibold text-indigo-300 font-mono")
                                        ui.badge(ch.get("chart_type", "plotly").upper(), color="indigo-950").classes("text-[10px] text-indigo-400 border border-indigo-800/50")
                                    ui.plotly(spec).classes("w-full min-h-[350px]")

                # Expandable code blocks
                if python_script:
                    with ui.expansion("Generated ML Python Script", icon="terminal").props("dense default-opened=false").classes("w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"):
                        ui.code(python_script, language="python").classes("w-full text-xs")

                if sql_query:
                    with ui.expansion("Generated SQL Statement", icon="code").props("dense default-opened=false").classes("w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"):
                        ui.code(sql_query, language="sql").classes("w-full text-xs")

        # Update right-hand workspace if requested
        if update_workspace:
            if dataset_data and dataset_data.get("columns") and dataset_data.get("rows"):
                studio.current_dataset_rows = dataset_data["rows"]
                studio.current_dataset_columns = [c["name"] for c in dataset_data["columns"]]
                studio.current_csv_name = dataset_data.get("file_name", "dataset.csv")

                table_widget.columns = dataset_data["columns"]
                table_widget.rows = dataset_data["rows"]
                table_widget.row_key = dataset_data["columns"][0]["name"] if dataset_data["columns"] else "id"
                table_widget.update()
                empty_state.set_visibility(False)
                table_widget.set_visibility(True)

                rows_badge.text = f"{len(dataset_data['rows'])} rows"
                cols_badge.text = f"{len(dataset_data['columns'])} cols"
                file_badge.text = dataset_data.get("file_name", "Dataset")
                download_btn.enable()

            if charts_data:
                plots_container.clear()
                plots_badge.text = f"{len(charts_data)} charts"
                plots_empty.set_visibility(False)
                with plots_container:
                    for ch in charts_data:
                        spec = ch.get("spec")
                        if spec:
                            with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md"):
                                with ui.row().classes("w-full justify-between items-center mb-2"):
                                    ui.label(ch.get("title", "Interactive Plotly Chart")).classes("text-sm font-semibold text-slate-200 font-mono")
                                    ui.badge(ch.get("chart_type", "plotly").upper(), color="indigo-900").classes("text-xs text-indigo-300 font-mono")
                                ui.plotly(spec).classes("w-full min-h-[480px]")
                workspace_tabs.value = tab_plots

            if python_script or sql_query:
                code_container.clear()
                code_empty.set_visibility(False)
                with code_container:
                    if python_script:
                        with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md"):
                            ui.label("Machine Learning Python Script").classes("text-xs font-semibold text-emerald-400 mb-2")
                            ui.code(python_script, language="python").classes("w-full text-xs")
                    if sql_query:
                        with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md"):
                            ui.label("PostgreSQL Query Statement").classes("text-xs font-semibold text-indigo-400 mb-2")
                            ui.code(sql_query, language="sql").classes("w-full text-xs")

    # -------------------------------------------------------------
    # Session Management Functions
    # -------------------------------------------------------------
    async def switch_to_session(session_id: str) -> None:
        """
        Loads and renders all messages and artifacts for the selected session.
        """
        detail = await studio.get_session_detail(session_id)
        if not detail:
            ui.notify(f"Could not load session {session_id}", type="negative")
            return

        studio.current_session_id = session_id
        studio.current_session_title = detail.get("title", "Session")
        active_session_badge.text = f"Session: {studio.current_session_title[:20]}"
        chat_title_label.text = studio.current_session_title

        # Clear existing messages in chat
        messages_container.clear()

        # If no messages, render welcome
        messages = detail.get("messages", [])
        if not messages:
            with messages_container:
                with ui.card().classes("w-full bg-slate-800/70 border border-slate-700/60 rounded-lg p-4"):
                    with ui.row().classes("items-center gap-2 mb-2"):
                        ui.avatar("smart_toy", color="indigo-600", text_color="white", size="sm")
                        ui.label("Orchestrator").classes("font-semibold text-xs text-indigo-300")
                    ui.markdown(
                        "Fresh session ready! Ask me any question, database query, or ML predictive task. "
                        "I remember our conversation context (last 3 messages) and active artifacts."
                    ).classes("text-sm text-slate-200 leading-relaxed")
        else:
            # Render all messages chronologically
            for i, msg in enumerate(messages):
                is_last_assistant = (i == len(messages) - 1 and msg.get("role") == "assistant")
                if msg.get("role") == "user":
                    render_user_message(msg.get("content", ""))
                else:
                    await render_assistant_message(
                        response_text=msg.get("content", ""),
                        metadata=msg.get("metadata", {}),
                        update_workspace=is_last_assistant,
                    )

        chat_scroll.scroll_to(percent=1.0)
        await refresh_sessions_list()
        ui.notify(f"Switched to session: {studio.current_session_title}", type="positive", position="top-right")

    async def handle_new_session() -> None:
        """
        Creates a fresh session and switches to it.
        """
        new_sess = await studio.create_session(title="New Session")
        if new_sess and "id" in new_sess:
            await switch_to_session(new_sess["id"])
            query_input.run_method("focus")

    async def handle_delete_session(session_id: str) -> None:
        """
        Deletes session and switches to another active session or creates a new one.
        """
        success = await studio.delete_session(session_id)
        if success:
            ui.notify("Session deleted", type="info", position="top-right")
            if studio.current_session_id == session_id:
                sessions = await studio.fetch_sessions()
                if sessions:
                    await switch_to_session(sessions[0]["id"])
                else:
                    await handle_new_session()
            else:
                await refresh_sessions_list()

    async def refresh_sessions_list() -> None:
        """
        Fetches session list from backend and updates cards in Sessions tab.
        """
        sessions = await studio.fetch_sessions()
        sessions_count_badge.text = f"{len(sessions)} sessions"
        sessions_list_container.clear()

        if not sessions:
            with sessions_list_container:
                with ui.card().classes("w-full bg-slate-900/60 border border-slate-800 p-8 text-center items-center"):
                    ui.icon("chat_bubble_outline", size="3rem").classes("text-slate-600 mb-2")
                    ui.label("No active sessions yet").classes("text-sm text-slate-400 font-semibold")
                    ui.label("Click '+ New Session' to begin a multi-turn chat.").classes("text-xs text-slate-500")
            return

        with sessions_list_container:
            for s in sessions:
                sid = s["id"]
                stitle = s.get("title", "New Session")
                msg_count = s.get("message_count", 0)
                updated_at = s.get("updated_at", "")[:19].replace("T", " ")
                last_msg = s.get("last_message", "")
                is_active = (sid == studio.current_session_id)

                card_classes = (
                    "w-full p-4 rounded-xl transition duration-150 "
                    + ("bg-indigo-950/40 border-2 border-indigo-500/70 shadow-lg" if is_active else "bg-slate-900/80 border border-slate-800 hover:border-slate-700")
                )

                with ui.card().classes(card_classes):
                    with ui.row().classes("w-full justify-between items-center"):
                        with ui.row().classes("items-center gap-2 flex-1"):
                            ui.icon("chat", size="1.1rem").classes("text-indigo-400" if is_active else "text-slate-500")
                            ui.label(stitle).classes("text-sm font-semibold text-slate-100 truncate max-w-sm")
                            if is_active:
                                ui.badge("Active", color="indigo-600").classes("text-[10px] font-mono px-2 py-0.5")
                            ui.badge(f"{msg_count} msgs", color="slate-800").classes("text-[10px] text-slate-400 font-mono")

                        with ui.row().classes("items-center gap-2"):
                            ui.label(updated_at).classes("text-[11px] text-slate-500 font-mono")
                            if not is_active:
                                ui.button("Open", icon="arrow_forward", on_click=lambda sid_val=sid: switch_to_session(sid_val)).props("dense outline color=indigo-400").classes("text-xs")
                            ui.button(icon="delete", on_click=lambda sid_val=sid: handle_delete_session(sid_val)).props("dense flat round color=rose-400").tooltip("Delete Session")

                    if last_msg:
                        ui.label(f'"{last_msg}"').classes("text-xs text-slate-400 italic pt-1 truncate w-full")

    # Wire navigation buttons
    new_session_header_btn.on_click(handle_new_session)
    new_session_chat_btn.on_click(handle_new_session)
    create_new_session_btn.on_click(handle_new_session)
    refresh_sessions_btn.on_click(refresh_sessions_list)
    browse_sessions_btn.on_click(lambda: setattr(workspace_tabs, "value", tab_sessions))

    # -------------------------------------------------------------
    # Query Submission Logic
    # -------------------------------------------------------------
    async def handle_submit() -> None:
        query_text = (query_input.value or "").strip()
        if not query_text or studio.is_busy:
            return

        studio.is_busy = True
        send_button.disable()
        query_input.value = ""

        # 1. Render User Message
        render_user_message(query_text)
        chat_scroll.scroll_to(percent=1.0)

        # 2. Render Temporary Thinking Indicator
        with messages_container:
            thinking_card = ui.card().classes("w-full bg-slate-800/50 border border-slate-700/40 rounded-lg p-3")
            with thinking_card:
                with ui.row().classes("items-center gap-3"):
                    ui.spinner("dots", size="sm", color="indigo-400")
                    ui.label("Thinking & executing multi-agent workflow with session memory...").classes("text-xs text-slate-400 italic")

        chat_scroll.scroll_to(percent=1.0)

        try:
            # 3. Call AI Service Endpoint with session_id
            result = await studio.send_query(query_text, session_id=studio.current_session_id)
            thinking_card.delete()

            returned_sid = result.get("session_id")
            if returned_sid:
                studio.current_session_id = returned_sid

            response_text = result.get("response", "Query completed.")
            metadata = result.get("metadata") or {}

            # 4. Render Assistant Message with artifacts
            await render_assistant_message(response_text, metadata, update_workspace=True)
            chat_scroll.scroll_to(percent=1.0)

            # 5. Sync session title & list
            sessions = await studio.fetch_sessions()
            for s in sessions:
                if s["id"] == studio.current_session_id:
                    studio.current_session_title = s.get("title", "Session")
                    active_session_badge.text = f"Session: {studio.current_session_title[:20]}"
                    chat_title_label.text = studio.current_session_title
                    break
            await refresh_sessions_list()

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

    # Initial session loading on mount
    async def init_session_state() -> None:
        sessions = await studio.fetch_sessions()
        if sessions:
            await switch_to_session(sessions[0]["id"])
        else:
            await handle_new_session()

    ui.timer(0.1, init_session_state, once=True)


def main() -> None:
    """
    Main entry point for starting the NiceGUI web server.
    """
    create_ui()
    ui.run(
        title="Multi-Agent System",
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
