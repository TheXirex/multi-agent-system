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
            "bg-[#212529] backdrop-blur-md border-b border-[#495057]/60 text-white px-4 py-0 flex items-center justify-between z-30 h-12"
        ):
            # Left side: Sidebar Toggle & Brand Logo
            with ui.row().classes("items-center gap-3"):
                ui.button(
                    icon="menu",
                    color=None,
                    on_click=self.on_toggle_sidebar,
                ).props("flat dense").classes("text-[#ced4da] hover:text-[#f8f9fa] rounded-[6px]").tooltip("Toggle Sessions Sidebar")

                ui.label("Multi-Agent Studio").classes("font-bold text-sm tracking-wide text-[#f8f9fa]")

                # Active Session Title
                with ui.row().classes("items-center gap-2 pl-3 border-l border-[#495057]/60 hidden md:flex"):
                    self.session_title_label = ui.label(self.state.current_session_title).classes(
                        "text-xs font-medium text-[#ced4da] max-w-xs truncate"
                    )

            # Right side: (Clean minimal header without clutter)
            with ui.row().classes("items-center gap-2"):
                pass

    def update_session_title(self, title: str) -> None:
        """
        Updates the active session title displayed in the header.
        """
        self.state.current_session_title = title
        if self.session_title_label:
            self.session_title_label.text = title
