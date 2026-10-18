import asyncio
from typing import Any, Callable, Dict, List, Optional
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


class ChatComponent:
    """
    Renders the chat interface: messages thread, user/assistant cards,
    pending message file attachments, inline interactive Plotly charts,
    expandable code snippets, suggested queries, and input box.
    """

    def __init__(
        self,
        state: StudioState,
        on_send_query: Callable[..., Any],
        on_upload_file: Optional[Callable[[bytes, str], Any]] = None,
    ) -> None:
        self.state = state
        self.on_send_query = on_send_query
        self.on_upload_file = on_upload_file

        self.messages_scroll: Optional[ui.scroll_area] = None
        self.messages_container: Optional[ui.column] = None
        self.query_input: Optional[ui.input] = None
        self.send_button: Optional[ui.button] = None
        self.attach_button: Optional[ui.button] = None
        self.thinking_card: Optional[ui.card] = None
        self.upload_dialog: Optional[ui.dialog] = None
        self.attached_files: List[Dict[str, Any]] = []
        self.attachments_row: Optional[ui.row] = None

    def render(self) -> None:
        """
        Builds the chat container layout with scroll area, suggestions, and input bar.
        """
        # Upload / Attach dialog
        with ui.dialog() as self.upload_dialog, ui.card().classes(
            "bg-[#343a40] border border-[#495057] p-6 rounded-xl space-y-4 max-w-md w-full shadow-2xl"
        ):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("attach_file", size="sm").classes("text-[#ced4da]")
                    ui.label("Attach Dataset (CSV / Excel)").classes("font-semibold text-sm text-[#f8f9fa]")
                ui.button(icon="close", color=None, on_click=self.upload_dialog.close).props("flat round dense").classes("text-[#adb5bd] hover:text-[#f8f9fa]")

            ui.label(
                "Attach a .csv or .xlsx file to your message. Upon sending, the dataset will be ingested and bound specifically to this session."
            ).classes("text-xs text-[#ced4da] leading-relaxed")

            ui.upload(
                on_upload=self._handle_upload_event,
                auto_upload=True,
                max_files=1,
            ).props("accept='.csv,.xlsx,.xls' dark flat bordered").classes("w-full")

        with ui.card().classes(
            "flex flex-col h-full max-h-full bg-[#343a40]/60 border border-[#495057]/60 rounded-xl p-0 overflow-hidden shadow-lg w-full min-w-0"
        ):
            # 1. Chat Messages Thread (Scroll Area)
            self.messages_scroll = ui.scroll_area().classes("flex-1 w-full p-4 overflow-x-hidden")
            with self.messages_scroll:
                self.messages_container = ui.column().classes("w-full max-w-full gap-4 overflow-hidden")

            # 2. Chat Input Box Form
            with ui.column().classes("w-full border-t border-[#495057]/60 bg-[#212529] p-3 gap-2 shrink-0"):
                # Pending attachments chip row
                self.attachments_row = ui.row().classes("w-full gap-2 flex-wrap hidden")

                with ui.row().classes("w-full items-center gap-2"):
                    self.attach_button = ui.button(
                        icon="attach_file",
                        color=None,
                        on_click=self.upload_dialog.open,
                    ).props("round flat dense").classes("text-[#ced4da] hover:text-[#f8f9fa]").tooltip("Attach CSV or Excel file (.csv, .xlsx)")

                    self.query_input = ui.input(
                        placeholder="Ask analytical question, request ML modeling, or refine charts... (Enter to send)",
                    ).props("outlined dense rounded autogrow clearable color=white").classes("flex-1 text-sm bg-[#343a40] text-[#f8f9fa]")

                    self.send_button = ui.button(
                        icon="send",
                        color=None,
                        on_click=self._submit_query,
                    ).props("rounded unelevated no-caps").classes("px-4 py-1.5 btn-light-accent font-bold transition-all")

                    self.query_input.on("keydown.enter", self._submit_query)

    async def _handle_upload_event(self, e: Any) -> None:
        """
        Attaches selected file to pending message state without calling backend immediately.
        """
        try:
            if self.upload_dialog:
                self.upload_dialog.close()

            file_bytes = await e.file.read()
            filename = getattr(e.file, "name", "dataset.csv")
            size_kb = len(file_bytes) / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"

            self.attached_files.append({
                "filename": filename,
                "file_bytes": file_bytes,
                "size_str": size_str,
            })
            self._refresh_attachment_chips()
            ui.notify(f"Attached '{filename}' ({size_str})", type="positive", position="top-right")
        except Exception as ex:
            ui.notify(f"Attachment error: {ex}", type="negative", position="top-right")

    def _remove_attachment(self, index: int) -> None:
        """
        Removes an attached file by index from pending attachments.
        """
        if 0 <= index < len(self.attached_files):
            removed = self.attached_files.pop(index)
            self._refresh_attachment_chips()
            ui.notify(f"Removed attachment '{removed.get('filename')}'", type="info", position="top-right")

    def _refresh_attachment_chips(self) -> None:
        """
        Renders attachment preview chips above the message input.
        """
        if not self.attachments_row:
            return

        self.attachments_row.clear()
        if not self.attached_files:
            self.attachments_row.classes(add="hidden")
            return

        self.attachments_row.classes(remove="hidden")
        with self.attachments_row:
            for idx, att in enumerate(self.attached_files):
                with ui.row().classes("items-center gap-1.5 bg-[#343a40] border border-[#6c757d]/60 text-[#f8f9fa] text-xs px-2.5 py-1 rounded-lg"):
                    ui.icon("attach_file", size="xs").classes("text-[#ced4da]")
                    ui.label(f"{att['filename']} ({att['size_str']})").classes("font-mono text-[11px]")
                    ui.button(
                        icon="close",
                        color=None,
                        on_click=lambda i=idx: self._remove_attachment(i),
                    ).props("flat round dense size=xs").classes("text-[#adb5bd] hover:text-[#f8f9fa]").tooltip("Remove attachment")

    async def _submit_query(self) -> None:
        if not self.query_input or self.state.is_busy:
            return
        query_text = (self.query_input.value or "").strip()
        if not query_text and not self.attached_files:
            return

        files_to_send = list(self.attached_files)
        self.query_input.value = ""
        self.attached_files.clear()
        self._refresh_attachment_chips()

        await self.on_send_query(query_text, files_to_send)

    def render_user_message(self, text: str, attachments: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Renders a user message bubble with optional attachment badges.
        """
        if not self.messages_container:
            return

        with self.messages_container:
            with ui.row().classes("w-full justify-end min-w-0"):
                with ui.card().classes(
                    "max-w-[85%] md:max-w-xl bg-[#495057] text-[#f8f9fa] p-3.5 rounded-2xl rounded-tr-sm shadow-md space-y-1.5 break-words overflow-hidden border border-[#6c757d]/60"
                ):
                    with ui.row().classes("items-center justify-between gap-3 text-xs opacity-90"):
                        ui.label("You").classes("font-semibold text-[11px] text-[#f8f9fa]")

                    if attachments:
                        with ui.row().classes("gap-1.5 flex-wrap"):
                            for att in attachments:
                                fn = att.get("filename", "dataset.csv")
                                size_info = f" ({att.get('size_str')})" if att.get("size_str") else ""
                                with ui.row().classes("items-center gap-1 bg-[#343a40] border border-[#6c757d]/60 text-[#ced4da] text-[11px] px-2 py-0.5 rounded"):
                                    ui.icon("attach_file", size="xs").classes("text-[#ced4da]")
                                    ui.label(f"{fn}{size_info}").classes("font-mono truncate max-w-[200px]")

                    if text:
                        ui.label(text).classes("text-sm leading-relaxed whitespace-pre-wrap break-words")

        self.scroll_to_bottom()

    def render_assistant_message(
        self,
        response_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        dataset_data: Optional[Dict[str, Any]] = None,
        charts_data: Optional[List[Dict[str, Any]]] = None,
        python_script: Optional[str] = None,
        sql_query: Optional[str] = None,
    ) -> None:
        """
        Renders an assistant response message card with text, metadata badges,
        inline interactive Plotly charts, and expandable code snippets.
        """
        if not self.messages_container:
            return

        meta = metadata or {}
        dataset_id = meta.get("dataset_id")

        with self.messages_container:
            with ui.card().classes("w-full max-w-full bg-[#343a40]/80 border border-[#495057]/70 rounded-xl p-4 space-y-3 shadow-md overflow-hidden min-w-0"):
                # Header row: Agent identity + metadata badges
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.row().classes("items-center gap-2"):
                        ui.avatar("smart_toy", size="xs").classes("bg-[#f8f9fa] text-[#212529] font-bold")
                        ui.label("Orchestrator Agent").classes("font-semibold text-xs text-[#f8f9fa]")

                    with ui.row().classes("items-center gap-1.5 flex-wrap"):
                        if dataset_id:
                            ds_name = dataset_data.get("name", f"dataset_{dataset_id}") if dataset_data else f"dataset_{dataset_id}"
                            ui.badge(f"Dataset #{dataset_id}: {ds_name}").classes("bg-[#212529] text-[#ced4da] border border-[#495057]/70 text-[10px] font-mono truncate max-w-[220px]")
                        if charts_data:
                            ui.badge(f"{len(charts_data)} Plotly Chart{'s' if len(charts_data) > 1 else ''}").classes("bg-[#212529] text-[#f8f9fa] border border-[#6c757d]/70 text-[10px] font-mono")

                # Markdown text content
                ui.markdown(response_text).classes("text-sm text-[#dee2e6] leading-relaxed break-words overflow-x-auto max-w-full")

                # Inline Plotly charts preview
                if charts_data:
                    with ui.column().classes("w-full max-w-full gap-3 pt-2 overflow-hidden"):
                        ui.label("Interactive Visualizations:").classes("text-xs font-semibold text-[#ced4da]")
                        for ch in charts_data:
                            spec = ch.get("spec")
                            if spec and isinstance(spec, dict):
                                spec = sanitize_plotly_monochrome(spec)
                                with ui.card().classes("w-full max-w-full bg-[#212529] border border-[#495057]/70 p-3 rounded-lg overflow-hidden"):
                                    with ui.row().classes("w-full justify-between items-center mb-1"):
                                        ui.label(ch.get("title", "Interactive Plot")).classes("text-xs font-semibold text-[#f8f9fa] font-mono truncate max-w-[70%]")
                                        ui.badge(ch.get("chart_type", "plotly").upper()).classes("bg-[#343a40] text-[#ced4da] border border-[#6c757d]/50 text-[10px] shrink-0")
                                    ui.plotly(spec).classes("w-full min-h-[300px] max-w-full")

                # Expandable code blocks
                if python_script and python_script.strip():
                    with ui.expansion("Generated ML Python Script", icon="terminal").props("dense default-opened=false").classes(
                        "w-full max-w-full bg-[#212529] border border-[#495057]/70 rounded-md text-xs text-[#ced4da] overflow-hidden"
                    ):
                        with ui.element("div").classes("w-full max-w-full overflow-x-auto p-1"):
                            ui.code(python_script.strip(), language="python").classes("text-xs")

                if sql_query and sql_query.strip():
                    with ui.expansion("Generated SQL Statement", icon="code").props("dense default-opened=false").classes(
                        "w-full max-w-full bg-[#212529] border border-[#495057]/70 rounded-md text-xs text-[#ced4da] overflow-hidden"
                    ):
                        with ui.element("div").classes("w-full max-w-full overflow-x-auto p-1"):
                            ui.code(sql_query.strip(), language="sql").classes("text-xs")

        self.scroll_to_bottom()

    def show_thinking(self) -> None:
        """
        Displays temporary thinking indicator.
        """
        if not self.messages_container:
            return
        with self.messages_container:
            self.thinking_card = ui.card().classes("w-full bg-[#343a40]/90 border border-[#495057]/70 rounded-lg p-3")
            with self.thinking_card:
                with ui.row().classes("items-center gap-3"):
                    ui.spinner("dots", size="sm").classes("text-[#ced4da]")
                    ui.label("Thinking & executing multi-agent workflow...").classes("text-xs text-[#ced4da] italic")
        self.scroll_to_bottom()

    def hide_thinking(self) -> None:
        """
        Hides temporary thinking indicator.
        """
        if self.thinking_card:
            self.thinking_card.delete()
            self.thinking_card = None

    def clear_messages(self) -> None:
        """
        Clears all message cards from the thread.
        """
        if self.messages_container:
            self.messages_container.clear()

    def scroll_to_bottom(self) -> None:
        """
        Scrolls the chat container to the bottom.
        """
        if self.messages_scroll:
            self.messages_scroll.scroll_to(percent=1.0)
