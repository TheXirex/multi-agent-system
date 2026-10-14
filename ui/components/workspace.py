from typing import Any, Dict, List, Optional
from nicegui import ui
from ui.state import StudioState


class WorkspaceComponent:
    """
    Renders the right tabbed studio workspace:
    - Table Data explorer (interactive table with columns and sorting)
    - Visualizations gallery (interactive full-size Plotly charts)
    - Code & Scripts viewer (Python and SQL syntax highlighted)
    """

    def __init__(self, state: StudioState) -> None:
        self.state = state

        self.tabs: Optional[ui.tabs] = None
        self.tab_table: Optional[ui.tab] = None
        self.tab_plots: Optional[ui.tab] = None
        self.tab_code: Optional[ui.tab] = None

        self.table_widget: Optional[ui.table] = None
        self.table_empty_card: Optional[ui.card] = None
        self.dataset_badge: Optional[ui.badge] = None

        self.plots_container: Optional[ui.column] = None
        self.plots_empty_card: Optional[ui.card] = None

        self.code_container: Optional[ui.column] = None
        self.code_empty_card: Optional[ui.card] = None

    def render(self) -> None:
        """
        Builds the workspace container with tabs and panel views.
        """
        with ui.card().classes(
            "flex flex-col h-full bg-slate-900/60 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg w-full"
        ):
            # Workspace Tab Navigation Header
            with ui.row().classes("w-full px-4 py-2 border-b border-slate-800 items-center justify-between bg-slate-900/90"):
                with ui.tabs().props(
                    "dense no-caps inline-label indicator-color=indigo-400 active-color=indigo-400 text-color=slate-400"
                ) as self.tabs:
                    self.tab_table = ui.tab("Table Data", icon="table_chart")
                    self.tab_plots = ui.tab("Visualizations", icon="insights")
                    self.tab_code = ui.tab("Code & Scripts", icon="code")

                with ui.row().classes("items-center gap-2"):
                    self.dataset_badge = ui.badge("No active dataset", color="slate-800").classes("text-[10px] text-slate-400 font-mono")

            # Tab Panels Container
            with ui.tab_panels(self.tabs, value=self.tab_table).classes("w-full flex-1 p-4 bg-slate-950/40 overflow-hidden"):
                # ==========================================
                # PANEL 1: TABLE DATA
                # ==========================================
                with ui.tab_panel(self.tab_table).classes("p-0 h-full flex flex-col"):
                    with ui.card().classes("w-full h-full bg-slate-900/40 border border-slate-800/80 rounded-lg p-3 flex flex-col"):
                        with ui.card().classes(
                            "w-full h-full flex items-center justify-center border border-dashed border-slate-800 bg-slate-900/20 text-center p-8 rounded-lg"
                        ) as self.table_empty_card:
                            ui.icon("table_rows", size="3rem").classes("text-slate-600 mb-2")
                            ui.label("No tabular dataset extracted yet").classes("text-sm text-slate-400 font-semibold")
                            ui.label("Ask a question to query database records or run analytics.").classes("text-xs text-slate-500")

                        self.table_widget = ui.table(
                            columns=[],
                            rows=[],
                            row_key="id",
                            pagination={"rowsPerPage": 15},
                        ).props("dense flat bordered dark virtual-scroll").classes("w-full flex-1")
                        self.table_widget.set_visibility(False)

                # ==========================================
                # PANEL 2: VISUALIZATIONS
                # ==========================================
                with ui.tab_panel(self.tab_plots).classes("p-0 h-full flex flex-col"):
                    with ui.scroll_area().classes("h-full w-full"):
                        with ui.card().classes(
                            "w-full h-full flex items-center justify-center border border-dashed border-slate-800 bg-slate-900/20 text-center p-12 rounded-lg"
                        ) as self.plots_empty_card:
                            ui.icon("bar_chart", size="3rem").classes("text-slate-600 mb-2")
                            ui.label("No interactive charts generated yet").classes("text-sm text-slate-400 font-semibold")
                            ui.label("Ask for an interactive visualization, distribution, or model plot.").classes("text-xs text-slate-500")

                        self.plots_container = ui.column().classes("w-full gap-4")

                # ==========================================
                # PANEL 3: CODE & SCRIPTS
                # ==========================================
                with ui.tab_panel(self.tab_code).classes("p-0 h-full flex flex-col"):
                    with ui.scroll_area().classes("h-full w-full"):
                        with ui.card().classes(
                            "w-full h-full flex items-center justify-center border border-dashed border-slate-800 bg-slate-900/20 text-center p-12 rounded-lg"
                        ) as self.code_empty_card:
                            ui.icon("terminal", size="3rem").classes("text-slate-600 mb-2")
                            ui.label("No scripts or queries executed yet").classes("text-sm text-slate-400 font-semibold")
                            ui.label("Code and SQL statements generated by agents appear here.").classes("text-xs text-slate-500")

                        self.code_container = ui.column().classes("w-full gap-4")

    def update_workspace(
        self,
        dataset_data: Optional[Dict[str, Any]] = None,
        charts_data: Optional[List[Dict[str, Any]]] = None,
        python_script: Optional[str] = None,
        sql_query: Optional[str] = None,
    ) -> None:
        """
        Updates the Table, Plotly Charts, and Code panels with new artifacts.
        """
        # 1. Update Table Data
        if dataset_data and dataset_data.get("columns") and dataset_data.get("rows"):
            rows = dataset_data["rows"]
            cols = dataset_data["columns"]
            ds_name = dataset_data.get("name", "dataset")

            if self.dataset_badge:
                self.dataset_badge.text = f"{ds_name} ({len(rows)} rows)"

            if self.table_widget:
                self.table_widget.columns = cols
                self.table_widget.rows = rows
                self.table_widget.row_key = cols[0]["name"] if cols else "id"
                self.table_widget.update()
                self.table_widget.set_visibility(True)

            if self.table_empty_card:
                self.table_empty_card.set_visibility(False)
        else:
            if self.dataset_badge:
                self.dataset_badge.text = "No active dataset"
            if self.table_widget:
                self.table_widget.set_visibility(False)
            if self.table_empty_card:
                self.table_empty_card.set_visibility(True)

        # 2. Update Visualizations Tab
        if self.plots_container and self.plots_empty_card:
            self.plots_container.clear()
            if charts_data:
                self.plots_empty_card.set_visibility(False)
                with self.plots_container:
                    for ch in charts_data:
                        spec = ch.get("spec")
                        if spec:
                            title = ch.get("title", "Interactive Visualization")
                            chart_type = ch.get("chart_type", "plotly")
                            with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md space-y-2"):
                                with ui.row().classes("w-full justify-between items-center"):
                                    ui.label(title).classes("text-sm font-semibold text-slate-100 font-mono")
                                    ui.badge(chart_type.upper(), color="indigo-950").classes("text-[10px] text-indigo-400 border border-indigo-800/40")
                                ui.plotly(spec).classes("w-full min-h-[420px]")
            else:
                self.plots_empty_card.set_visibility(True)

        # 3. Update Code & Scripts Tab
        has_code = False
        if self.code_container and self.code_empty_card:
            self.code_container.clear()
            with self.code_container:
                if python_script and python_script.strip():
                    has_code = True
                    with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md"):
                        with ui.row().classes("w-full justify-between items-center mb-2"):
                            ui.label("Machine Learning Python Script").classes("text-xs font-semibold text-emerald-400 font-mono")
                            ui.badge("PYTHON", color="emerald-950").classes("text-[10px] text-emerald-400 border border-emerald-800/40")
                        ui.code(python_script.strip(), language="python").classes("w-full text-xs")
                if sql_query and sql_query.strip():
                    has_code = True
                    with ui.card().classes("w-full bg-slate-900/90 border border-slate-800 p-4 rounded-xl shadow-md"):
                        with ui.row().classes("w-full justify-between items-center mb-2"):
                            ui.label("PostgreSQL Query Statement").classes("text-xs font-semibold text-indigo-400 font-mono")
                            ui.badge("SQL", color="indigo-950").classes("text-[10px] text-indigo-400 border border-indigo-800/40")
                        ui.code(sql_query.strip(), language="sql").classes("w-full text-xs")

            self.code_empty_card.set_visibility(not has_code)

        # 4. Auto-switch active tab
        if self.tabs:
            has_table = bool(dataset_data and dataset_data.get("columns") and dataset_data.get("rows"))
            has_plots = bool(charts_data)
            if self.tabs.value == self.tab_code and has_code:
                pass
            elif self.tabs.value == self.tab_plots and has_plots:
                pass
            elif has_plots:
                self.tabs.value = self.tab_plots
            elif has_table:
                self.tabs.value = self.tab_table
            elif has_code:
                self.tabs.value = self.tab_code

