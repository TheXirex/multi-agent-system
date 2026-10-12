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
        self.current_dataset_rows: List[Dict[str, Any]] = []
        self.current_dataset_columns: List[str] = []
        self.current_csv_name: Optional[str] = None
        self.is_busy: bool = False

    async def send_query(self, query_text: str) -> Dict[str, Any]:
        """
        Sends natural language query to the AI service endpoint.

        Args:
            query_text (str): User request.

        Returns:
            Dict[str, Any]: Response from the AI service with ID-only metadata.
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.ai_service_url}/api/query",
                json={"query": query_text},
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
    Constructs the NiceGUI layout featuring chat on the left and tabbed workspace on the right.
    """
    studio = DBStudioUI()

    # Enable dark mode
    ui.dark_mode(value=True)

    # Top Navigation Header
    with ui.header().classes("w-full bg-slate-900 border-b border-slate-800 px-6 py-3 flex items-center justify-between shadow-md"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("hub", size="1.8rem").classes("text-indigo-400")
            ui.label("Multi-Agent System").classes("text-lg font-bold text-slate-100 tracking-wide")

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
                    ui.label("Chat").classes("font-semibold text-slate-200 text-sm")

            # Chat Messages Scroll Area
            chat_scroll = ui.scroll_area().classes("flex-1 p-5 space-y-4 overflow-y-auto")
            with chat_scroll:
                messages_container = ui.column().classes("w-full gap-4")

                # Welcome initial message
                with messages_container:
                    with ui.card().classes("w-full bg-slate-800/70 border border-slate-700/60 rounded-lg p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.avatar("smart_toy", color="indigo-600", text_color="white", size="sm")
                            ui.label("Orchestrator").classes("font-semibold text-xs text-indigo-300")
                        ui.markdown(
                            "Hello! I am your **Orchestrator Agent**. "
                            "Ask me any question or request data analysis. I coordinate specialized domain agents to "
                            "query the database, train ML models, and render interactive Plotly charts."
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
                        "Cluster customers by total orders and plot interactive clusters",
                        "Train a regression model to predict order amount and plot feature importances",
                    ]:
                        ui.chip(
                            prompt_text,
                            on_click=lambda p=prompt_text: set_and_send(p),
                        ).props("dense clickable outline color=indigo-400").classes("text-[11px]")

            # Chat Input Form
            with ui.row().classes("w-full p-4 border-t border-slate-800 bg-slate-900/90 items-center gap-2"):
                query_input = ui.input(
                    placeholder="Ask data query or ML task... (Press Enter to send)",
                ).props("outlined dense rounded autogrow clearable").classes("flex-1 text-sm bg-slate-800/50 text-white")

                send_button = ui.button(icon="send").props("rounded unelevated color=indigo-600")

        # ==========================================
        # RIGHT COLUMN: TABBED WORKSPACE (7 cols)
        # ==========================================
        with ui.card().classes("lg:col-span-7 flex flex-col h-full bg-slate-900/60 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg"):
            # Workspace Header with Navigation Tabs
            with ui.row().classes("w-full px-4 py-2 border-b border-slate-800 items-center justify-between bg-slate-900/90"):
                with ui.tabs().props("dense no-caps inline-label indicator-color=indigo-400 active-color=indigo-400 text-color=slate-400") as workspace_tabs:
                    tab_table = ui.tab("Table Data", icon="table_chart")
                    tab_plots = ui.tab("Visualizations", icon="insights")
                    tab_code = ui.tab("Code & Scripts", icon="code")

                with ui.row().classes("items-center gap-2"):
                    rows_badge = ui.badge("0 rows", color="slate-800").classes("text-xs text-slate-300 font-mono")
                    plots_badge = ui.badge("0 charts", color="slate-800").classes("text-xs text-slate-300 font-mono")
                    download_btn = ui.button(icon="download").props("flat round dense color=slate-400").tooltip("Download CSV")
                    download_btn.disable()

            with ui.tab_panels(workspace_tabs, value=tab_table).classes("flex-1 w-full p-0 bg-transparent overflow-hidden"):
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

    # Download button handler
    def handle_download() -> None:
        if studio.current_dataset_rows:
            df = pd.DataFrame(studio.current_dataset_rows)
            csv_str = df.to_csv(index=False)
            filename = studio.current_csv_name or "dataset.csv"
            ui.download(csv_str.encode("utf-8"), filename=filename)
        else:
            ui.notify("No dataset available to download", type="warning")

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
                    ui.label("Thinking & executing multi-agent workflow...").classes("text-xs text-slate-400 italic")

        chat_scroll.scroll_to(percent=1.0)

        try:
            # 3. Call AI Service Endpoint
            result = await studio.send_query(query_text)

            # Remove thinking indicator
            thinking_card.delete()

            response_text = result.get("response", "Query completed.")
            metadata = result.get("metadata") or {}

            # Retrieve entity IDs from ID-only metadata
            dataset_id = metadata.get("dataset_id")
            chart_id = metadata.get("chart_id")
            chart_ids = metadata.get("chart_ids") or ([chart_id] if chart_id else [])
            script_id = metadata.get("script_id")

            # Resolve entities from backend by ID
            dataset_data = None
            if dataset_id:
                dataset_data = await studio.fetch_dataset(dataset_id)
                if dataset_data:
                    studio.current_dataset_rows = dataset_data.get("rows", [])
                    studio.current_dataset_columns = [c["name"] for c in dataset_data.get("columns", [])]
                    studio.current_csv_name = dataset_data.get("file_name", "dataset.csv")

            charts_data = []
            for cid in chart_ids:
                c_obj = await studio.fetch_chart(cid)
                if c_obj:
                    charts_data.append(c_obj)

            script_data = None
            if script_id:
                script_data = await studio.fetch_script(script_id)

            sql_query = dataset_data.get("query", "") if dataset_data else ""
            python_script = script_data.get("script", "") if script_data else ""

            # 4. Render Assistant Message in Chat
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

                    # Inline Plotly charts preview in chat
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

                    # Expandable code blocks in chat
                    if python_script:
                        with ui.expansion("Generated ML Python Script", icon="terminal").props("dense default-opened=false").classes("w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"):
                            ui.code(python_script, language="python").classes("w-full text-xs")

                    if sql_query:
                        with ui.expansion("Generated SQL Statement", icon="code").props("dense default-opened=false").classes("w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"):
                            ui.code(sql_query, language="sql").classes("w-full text-xs")

            chat_scroll.scroll_to(percent=1.0)

            # 5. Populate Table Data Tab
            if dataset_data and dataset_data.get("columns") and dataset_data.get("rows"):
                columns = dataset_data["columns"]
                rows = dataset_data["rows"]
                table_widget.columns = columns
                table_widget.rows = rows
                table_widget.row_key = columns[0]["name"] if columns else "id"
                table_widget.update()

                empty_state.set_visibility(False)
                table_widget.set_visibility(True)

                rows_badge.text = f"{len(rows)} rows"
                cols_badge.text = f"{len(columns)} cols"
                file_badge.text = dataset_data.get("file_name", "Dataset")
                download_btn.enable()
            else:
                empty_state.set_visibility(True)
                table_widget.set_visibility(False)
                rows_badge.text = "0 rows"
                cols_badge.text = "0 cols"
                file_badge.text = "Empty result"
                download_btn.disable()

            # 6. Populate Visualizations Tab
            plots_container.clear()
            plots_badge.text = f"{len(charts_data)} charts"
            if charts_data:
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
            else:
                plots_empty.set_visibility(True)

            # 7. Populate Code Tab
            code_container.clear()
            has_code = False
            with code_container:
                if python_script:
                    has_code = True
                    with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md"):
                        ui.label("Machine Learning Python Script").classes("text-xs font-semibold text-emerald-400 mb-2")
                        ui.code(python_script, language="python").classes("w-full text-xs")
                if sql_query:
                    has_code = True
                    with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md"):
                        ui.label("PostgreSQL Query Statement").classes("text-xs font-semibold text-indigo-400 mb-2")
                        ui.code(sql_query, language="sql").classes("w-full text-xs")

            code_empty.set_visibility(not has_code)

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
