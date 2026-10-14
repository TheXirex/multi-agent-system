import asyncio
from typing import Any, Callable, Dict, List, Optional
from nicegui import ui
from ui.state import StudioState

SUGGESTED_QUERIES = [
    "Show table structures and summary distributions of available data",
    "Extract the primary numerical and categorical attributes into a dataset",
    "Train a regression model on primary numerical values and plot feature importances",
    "Change the previous visualization into an interactive scatter plot with trendline",
    "Cluster records into segments based on numerical features and plot the clusters",
]


class ChatComponent:
    """
    Renders the chat interface: messages thread, user/assistant cards,
    inline interactive Plotly charts, expandable code snippets, suggested queries, and input box.
    """

    def __init__(
        self,
        state: StudioState,
        on_send_query: Callable[[str], Any],
    ) -> None:
        self.state = state
        self.on_send_query = on_send_query

        self.messages_scroll: Optional[ui.scroll_area] = None
        self.messages_container: Optional[ui.column] = None
        self.query_input: Optional[ui.input] = None
        self.send_button: Optional[ui.button] = None
        self.thinking_card: Optional[ui.card] = None

    def render(self) -> None:
        """
        Builds the chat container layout with scroll area, suggestions, and input bar.
        """
        with ui.card().classes(
            "flex flex-col h-full bg-slate-900/60 border border-slate-800 rounded-xl p-0 overflow-hidden shadow-lg w-full"
        ):
            # 1. Chat Messages Thread (Scroll Area)
            self.messages_scroll = ui.scroll_area().classes("flex-1 p-5 space-y-4 overflow-y-auto")
            with self.messages_scroll:
                self.messages_container = ui.column().classes("w-full gap-4")

            # 2. Database-Agnostic Suggested Query Chips
            with ui.column().classes("w-full px-4 pt-2.5 pb-2 border-t border-slate-800/80 bg-slate-900/40"):
                ui.label("Suggested Analytical Queries & Refinements:").classes("text-[11px] font-medium text-slate-400")
                with ui.row().classes("gap-1.5 flex-wrap"):
                    for prompt_text in SUGGESTED_QUERIES:
                        ui.chip(
                            prompt_text,
                            on_click=lambda p=prompt_text: self._handle_suggestion_click(p),
                        ).props("dense clickable outline color=indigo-400").classes("text-[11px] hover:bg-indigo-950/40")

            # 3. Chat Input Box Form
            with ui.row().classes("w-full p-3.5 border-t border-slate-800 bg-slate-900/90 items-center gap-2"):
                self.query_input = ui.input(
                    placeholder="Ask analytical question, request ML modeling, or refine charts... (Enter to send)",
                ).props("outlined dense rounded autogrow clearable").classes("flex-1 text-sm bg-slate-800/50 text-white")

                self.send_button = ui.button(
                    icon="send",
                    on_click=self._submit_query,
                ).props("rounded unelevated color=indigo-600").classes("px-4")

                self.query_input.on("keydown.enter", self._submit_query)

    async def _handle_suggestion_click(self, prompt: str) -> None:
        if self.state.is_busy or not self.query_input:
            return
        self.query_input.value = prompt
        await self._submit_query()

    async def _submit_query(self) -> None:
        if not self.query_input or self.state.is_busy:
            return
        query_text = (self.query_input.value or "").strip()
        if not query_text:
            return

        self.query_input.value = ""
        await self.on_send_query(query_text)

    def render_user_message(self, text: str) -> None:
        """
        Renders a user message bubble.
        """
        if not self.messages_container:
            return

        with self.messages_container:
            with ui.row().classes("w-full justify-end"):
                with ui.card().classes(
                    "max-w-xl bg-indigo-600/90 text-white p-3.5 rounded-2xl rounded-tr-sm shadow-md space-y-1"
                ):
                    with ui.row().classes("items-center justify-between gap-3 text-xs opacity-80"):
                        ui.label("You").classes("font-semibold text-[11px]")
                    ui.label(text).classes("text-sm leading-relaxed whitespace-pre-wrap")

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
            with ui.card().classes("w-full bg-slate-800/70 border border-slate-700/60 rounded-xl p-4 space-y-3 shadow-md"):
                # Header row: Agent identity + metadata badges
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.row().classes("items-center gap-2"):
                        ui.avatar("smart_toy", color="indigo-600", text_color="white", size="xs")
                        ui.label("Orchestrator Agent").classes("font-semibold text-xs text-indigo-300")

                    with ui.row().classes("items-center gap-1.5"):
                        if dataset_id:
                            ds_name = dataset_data.get("name", f"dataset_{dataset_id}") if dataset_data else f"dataset_{dataset_id}"
                            ui.badge(f"Dataset #{dataset_id}: {ds_name}", color="slate-900").classes("text-[10px] text-slate-400 font-mono")
                        if charts_data:
                            ui.badge(f"{len(charts_data)} Plotly Chart{'s' if len(charts_data) > 1 else ''}", color="indigo-900").classes("text-[10px] text-indigo-300 font-mono")

                # Markdown text content
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
                if python_script and python_script.strip():
                    with ui.expansion("Generated ML Python Script", icon="terminal").props("dense default-opened=false").classes(
                        "w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"
                    ):
                        ui.code(python_script.strip(), language="python").classes("w-full text-xs")

                if sql_query and sql_query.strip():
                    with ui.expansion("Generated SQL Statement", icon="code").props("dense default-opened=false").classes(
                        "w-full bg-slate-900/60 border border-slate-800/80 rounded-md text-xs text-slate-300"
                    ):
                        ui.code(sql_query.strip(), language="sql").classes("w-full text-xs")


        self.scroll_to_bottom()

    def show_thinking(self) -> None:
        """
        Displays temporary thinking indicator.
        """
        if not self.messages_container:
            return
        with self.messages_container:
            self.thinking_card = ui.card().classes("w-full bg-slate-800/50 border border-slate-700/40 rounded-lg p-3")
            with self.thinking_card:
                with ui.row().classes("items-center gap-3"):
                    ui.spinner("dots", size="sm", color="indigo-400")
                    ui.label("Thinking & executing multi-agent workflow...").classes("text-xs text-slate-400 italic")
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
