from typing import Any, Dict, List, Optional
from nicegui import ui
from ui.state import StudioState


def sanitize_plotly_monochrome(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Guarantees strict monochrome styling on Plotly specifications:
    eliminates default blue/cyan/vibrant colors, applying the 9-shade grayscale theme.
    """
    if not isinstance(spec, dict):
        return spec

    mono_palette = [
        "#f8f9fa",
        "#ced4da",
        "#adb5bd",
        "#6c757d",
        "#dee2e6",
        "#e9ecef",
        "#495057",
    ]

    layout = spec.setdefault("layout", {})
    layout["autosize"] = True
    layout.pop("width", None)
    layout["paper_bgcolor"] = "#212529"
    layout["plot_bgcolor"] = "#212529"
    layout["font"] = {"color": "#f8f9fa"}
    layout["colorway"] = mono_palette

    if "template" in layout:
        if isinstance(layout["template"], dict):
            t_layout = layout["template"].setdefault("layout", {})
            t_layout["colorway"] = mono_palette
            t_layout["paper_bgcolor"] = "#212529"
            t_layout["plot_bgcolor"] = "#212529"
            t_layout["font"] = {"color": "#f8f9fa"}
        else:
            layout.pop("template", None)

    for k in list(layout.keys()):
        if k.startswith("xaxis") or k.startswith("yaxis"):
            axis = layout[k]
            if isinstance(axis, dict):
                axis["gridcolor"] = "#343a40"
                axis["zerolinecolor"] = "#495057"
                axis["linecolor"] = "#495057"
                axis["tickcolor"] = "#6c757d"
                axis["tickfont"] = {"color": "#ced4da"}
                axis["titlefont"] = {"color": "#f8f9fa"}

    traces = spec.get("data", [])
    if isinstance(traces, list):
        for i, tr in enumerate(traces):
            if not isinstance(tr, dict):
                continue
            mono_c = mono_palette[i % len(mono_palette)]
            marker = tr.get("marker")
            if isinstance(marker, dict):
                mc = marker.get("color")
                if not mc or (isinstance(mc, str) and any(b in mc.lower() for b in ("636efa", "1976d2", "1f77b4", "blue", "cyan", "sky", "indigo", "#0000ff"))):
                    marker["color"] = mono_c
                if "colorscale" in marker:
                    marker["colorscale"] = "Greys"
            elif marker is None and tr.get("type") in ("scatter", "bar", "pie"):
                tr["marker"] = {"color": mono_c}

            line = tr.get("line")
            if isinstance(line, dict):
                lc = line.get("color")
                if not lc or (isinstance(lc, str) and any(b in lc.lower() for b in ("636efa", "1976d2", "1f77b4", "blue", "cyan", "sky", "indigo", "#0000ff"))):
                    line["color"] = mono_c
            elif line is None and tr.get("type") in ("scatter", "scattergl", "line"):
                tr["line"] = {"color": mono_c}

    return spec


class WorkspaceComponent:
    """
    Renders the right studio workspace with tabbed navigation:
    1. Table Data (interactive data table with pagination)
    2. Visualizations (Plotly interactive charts)
    3. Code & Scripts (generated Python scripts and SQL queries)
    """

    def __init__(self, state: StudioState) -> None:
        self.state = state

        # Tabs navigation
        self.tabs: Optional[ui.tabs] = None
        self.tab_table: Optional[ui.tab] = None
        self.tab_plots: Optional[ui.tab] = None
        self.tab_code: Optional[ui.tab] = None

        # Header dataset badge
        self.dataset_badge: Optional[ui.badge] = None

        # Tab 1: Table Data
        self.table_widget: Optional[ui.table] = None
        self.table_empty_card: Optional[ui.column] = None

        # Tab 2: Visualizations
        self.plots_empty_card: Optional[ui.column] = None
        self.plots_container: Optional[ui.column] = None

        # Tab 3: Code & Scripts
        self.code_empty_card: Optional[ui.column] = None
        self.code_container: Optional[ui.column] = None

    def render(self) -> None:
        """
        Builds the workspace container featuring tabbed navigation.
        """
        with ui.card().classes(
            "flex flex-col h-full max-h-full bg-[#343a40]/60 border border-[#495057]/60 rounded-xl p-0 overflow-hidden shadow-lg w-full min-w-0"
        ):
            # Header Row with Tabs and Dataset Badge
            with ui.row().classes(
                "w-full px-3 py-1.5 border-b border-[#495057]/60 bg-[#212529] items-center justify-between shrink-0"
            ):
                with ui.tabs().classes("text-[#adb5bd]").props("dense no-caps active-color=white indicator-color=white") as self.tabs:
                    self.tab_table = ui.tab("Table Data", icon="table_chart").classes("text-xs font-semibold text-[#adb5bd] hover:text-[#f8f9fa]")
                    self.tab_plots = ui.tab("Visualizations", icon="insights").classes("text-xs font-semibold text-[#adb5bd] hover:text-[#f8f9fa]")
                    self.tab_code = ui.tab("Code & Scripts", icon="code").classes("text-xs font-semibold text-[#adb5bd] hover:text-[#f8f9fa]")

                self.dataset_badge = ui.badge("").classes(
                    "bg-[#343a40] text-[#f8f9fa] font-mono text-[10px] border border-[#6c757d]/60 hidden"
                )

            # Tab Panels Container
            with ui.tab_panels(self.tabs, value=self.tab_table).classes("w-full flex-1 bg-transparent p-3 min-h-0 overflow-hidden"):

                # ==========================================
                # PANEL 1: TABLE DATA
                # ==========================================
                with ui.tab_panel(self.tab_table).classes("p-0 h-full flex flex-col min-h-0 overflow-hidden"):
                    with ui.card().classes("w-full h-full bg-[#212529]/80 border border-[#495057]/60 rounded-lg p-2.5 flex flex-col min-h-0 overflow-hidden"):
                        with ui.column().classes(
                            "w-full h-full flex items-center justify-center border border-dashed border-[#495057]/70 bg-[#343a40]/30 text-center p-8 rounded-lg"
                        ) as self.table_empty_card:
                            ui.icon("table_rows", size="2.5rem").classes("text-[#6c757d] mb-2")
                            ui.label("No tabular dataset loaded yet").classes("text-sm text-[#ced4da] font-semibold")
                            ui.label("Ask a question to query database records or run analytics.").classes("text-xs text-[#adb5bd]")

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
                with ui.tab_panel(self.tab_plots).classes("p-0 h-full flex flex-col min-h-0 overflow-hidden"):
                    with ui.scroll_area().classes("h-full w-full overflow-x-hidden"):
                        with ui.column().classes(
                            "w-full h-full flex items-center justify-center border border-dashed border-[#495057]/70 bg-[#343a40]/30 text-center p-12 rounded-lg"
                        ) as self.plots_empty_card:
                            ui.icon("insights", size="2.5rem").classes("text-[#6c757d] mb-2")
                            ui.label("No interactive charts generated yet").classes("text-sm text-[#ced4da] font-semibold")
                            ui.label("Ask for an interactive visualization, distribution, or model plot.").classes("text-xs text-[#adb5bd]")

                        self.plots_container = ui.column().classes("w-full max-w-full gap-4 overflow-hidden")

                # ==========================================
                # PANEL 3: CODE & SCRIPTS
                # ==========================================
                with ui.tab_panel(self.tab_code).classes("p-0 h-full flex flex-col min-h-0 overflow-hidden"):
                    with ui.scroll_area().classes("h-full w-full overflow-x-hidden"):
                        with ui.column().classes(
                            "w-full h-full flex items-center justify-center border border-dashed border-[#495057]/70 bg-[#343a40]/30 text-center p-12 rounded-lg"
                        ) as self.code_empty_card:
                            ui.icon("terminal", size="2.5rem").classes("text-[#6c757d] mb-2")
                            ui.label("No scripts or queries executed yet").classes("text-sm text-[#ced4da] font-semibold")
                            ui.label("Code and SQL statements generated by agents appear here.").classes("text-xs text-[#adb5bd]")

                        self.code_container = ui.column().classes("w-full max-w-full gap-4 overflow-hidden")

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
                self.dataset_badge.classes(remove="hidden")

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
                self.dataset_badge.classes(add="hidden")
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
                        if spec and isinstance(spec, dict):
                            spec = sanitize_plotly_monochrome(spec)
                            title = ch.get("title", "Interactive Visualization")
                            chart_type = ch.get("chart_type", "plotly")
                            with ui.card().classes("w-full max-w-full bg-[#212529] border border-[#495057]/70 p-3.5 rounded-xl shadow-md space-y-2 overflow-hidden"):
                                with ui.row().classes("w-full justify-between items-center"):
                                    ui.label(title).classes("text-xs font-semibold text-[#f8f9fa] font-mono truncate max-w-[70%]")
                                    ui.badge(chart_type.upper()).classes("bg-[#343a40] text-[#ced4da] border border-[#6c757d]/50 text-[10px] shrink-0")
                                ui.plotly(spec).classes("w-full min-h-[380px] max-w-full")
            else:
                self.plots_empty_card.set_visibility(True)

        # 3. Update Code & Scripts Tab
        has_code = False
        if self.code_container and self.code_empty_card:
            self.code_container.clear()
            with self.code_container:
                if python_script and python_script.strip():
                    has_code = True
                    with ui.card().classes("w-full max-w-full bg-[#212529] border border-[#495057]/70 p-3.5 rounded-xl shadow-md overflow-hidden"):
                        with ui.row().classes("w-full justify-between items-center mb-2"):
                            ui.label("Machine Learning Python Script").classes("text-xs font-semibold text-[#ced4da] font-mono")
                            ui.badge("PYTHON").classes("bg-[#343a40] text-[#f8f9fa] border border-[#6c757d]/50 text-[10px] shrink-0")
                        with ui.element("div").classes("w-full max-w-full overflow-x-auto"):
                            ui.code(python_script.strip(), language="python").classes("text-xs")

                if sql_query and sql_query.strip():
                    has_code = True
                    with ui.card().classes("w-full max-w-full bg-[#212529] border border-[#495057]/70 p-3.5 rounded-xl shadow-md overflow-hidden"):
                        with ui.row().classes("w-full justify-between items-center mb-2"):
                            ui.label("PostgreSQL Query Statement").classes("text-xs font-semibold text-[#ced4da] font-mono")
                            ui.badge("SQL").classes("bg-[#343a40] text-[#f8f9fa] border border-[#6c757d]/50 text-[10px] shrink-0")
                        with ui.element("div").classes("w-full max-w-full overflow-x-auto"):
                            ui.code(sql_query.strip(), language="sql").classes("text-xs")

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
