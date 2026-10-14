from typing import Callable, Optional
from nicegui import ui
from ui.state import StudioState


class HeaderComponent:
    """
    Renders top application header with sidebar toggle, active session title,
    connection badge, and quick action buttons.
    """

    def __init__(
        self,
        state: StudioState,
        on_toggle_sidebar: Callable[[], None],
        on_new_chat: Callable[[], None],
    ) -> None:
        self.state = state
        self.on_toggle_sidebar = on_toggle_sidebar
        self.on_new_chat = on_new_chat

        self.title_badge: Optional[ui.badge] = None
        self.session_title_label: Optional[ui.label] = None

    def render(self) -> None:
        with ui.header().classes(
            "bg-slate-900/95 backdrop-blur-md border-b border-slate-800 text-white px-4 py-2.5 flex items-center justify-between z-30"
        ):
            # Left side: Sidebar Toggle & Brand Logo
            with ui.row().classes("items-center gap-3"):
                ui.button(
                    icon="menu",
                    on_click=self.on_toggle_sidebar,
                ).props("flat round dense color=slate-300").tooltip("Toggle Sessions Sidebar")

                with ui.row().classes("items-center gap-2"):
                    ui.avatar("hub", color="indigo-600", text_color="white", size="sm").classes("shadow-md shadow-indigo-500/20")
                    ui.label("Multi-Agent Studio").classes("font-bold text-sm tracking-wide text-white")

                # Active Session Title
                with ui.row().classes("items-center gap-2 pl-3 border-l border-slate-700/60 hidden md:flex"):
                    self.session_title_label = ui.label(self.state.current_session_title).classes(
                        "text-xs font-medium text-slate-300 max-w-xs truncate"
                    )

            # Right side: Status Indicator & Quick New Chat Button
            with ui.row().classes("items-center gap-3"):
                with ui.badge(color="slate-800").classes("text-[11px] font-mono text-emerald-400 border border-emerald-500/30 px-2 py-0.5 gap-1.5 flex items-center"):
                    ui.icon("fiber_manual_record", size="0.6rem").classes("text-emerald-400 animate-pulse")
                    ui.label("Service Online").classes("text-[10px]")

                ui.button(
                    "New Chat",
                    icon="add",
                    on_click=self.on_new_chat,
                ).props("dense unelevated color=indigo-600").classes("text-xs font-semibold px-3")

    def update_session_title(self, title: str) -> None:
        """
        Updates the active session title displayed in the header.
        """
        self.state.current_session_title = title
        if self.session_title_label:
            self.session_title_label.text = title
