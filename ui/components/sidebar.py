import asyncio
from typing import Any, Callable, Dict, List, Optional
from nicegui import ui
from ui.api_client import DBStudioClient
from ui.state import StudioState


class SidebarComponent:
    """
    Renders left drawer sidebar dedicated to chat sessions management:
    listing all sessions, highlighting active session, starting new session, and deleting.
    """

    def __init__(
        self,
        client: DBStudioClient,
        state: StudioState,
        on_select_session: Callable[[str], Any],
        on_create_session: Callable[[], Any],
    ) -> None:
        self.client = client
        self.state = state
        self.on_select_session = on_select_session
        self.on_create_session = on_create_session

        self.drawer: Optional[ui.left_drawer] = None
        self.sessions_list_container: Optional[ui.column] = None

    def render(self) -> ui.left_drawer:
        """
        Creates the Left Drawer sidebar with NiceGUI.
        """
        self.drawer = ui.left_drawer(value=True, bordered=True).props("width=280").classes(
            "bg-[#212529] border-r border-[#495057]/60 text-[#dee2e6] flex flex-col p-0 h-full z-20 overflow-hidden"
        )

        with self.drawer:
            # Top Section: New Chat Action
            with ui.column().classes("w-full p-3.5 border-b border-[#495057]/60 gap-2.5 shrink-0"):
                with ui.row().classes("w-full items-center gap-2"):
                    ui.icon("forum", size="1.05rem").classes("text-[#adb5bd]")
                    ui.label("Chat Sessions").classes("font-bold text-xs uppercase tracking-wider text-[#ced4da]")

                ui.button(
                    "New Chat",
                    icon="add",
                    color=None,
                    on_click=self._handle_create_click,
                ).props("unelevated no-caps").classes(
                    "w-full text-xs font-bold py-2 rounded-lg btn-light-accent shadow-sm transition-all"
                )

            # Middle Section: Scrollable Sessions List
            with ui.scroll_area().classes("flex-1 w-full px-2.5 py-2.5 overflow-x-hidden"):
                self.sessions_list_container = ui.column().classes("w-full gap-1.5 max-w-full overflow-hidden")

        return self.drawer

    def toggle(self) -> None:
        """
        Toggles sidebar drawer visibility.
        """
        if self.drawer:
            self.drawer.toggle()

    async def _handle_create_click(self) -> None:
        if self.state.is_busy:
            return
        await self.on_create_session()

    async def refresh_sessions(self, sessions: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Refreshes the sessions list rendered inside the sidebar.
        """
        if sessions is None:
            sessions = await self.client.fetch_sessions()

        if not self.sessions_list_container:
            return

        self.sessions_list_container.clear()

        if not sessions:
            with self.sessions_list_container:
                with ui.card().classes("w-full max-w-full bg-[#343a40]/50 border border-dashed border-[#495057]/70 p-6 text-center items-center rounded-xl"):
                    ui.icon("chat_bubble_outline", size="2rem").classes("text-[#6c757d] mb-1")
                    ui.label("No conversations yet").classes("text-xs text-[#ced4da] font-medium")
                    ui.label("Click '+ New Chat' to start").classes("text-[10px] text-[#adb5bd]")
            return

        with self.sessions_list_container:
            for s in sessions:
                sid = s.get("id", "")
                title = s.get("title", "New Session")
                is_active = (sid == self.state.current_session_id)

                item_classes = (
                    "w-full max-w-full box-border px-2.5 py-2 rounded-lg cursor-pointer transition-all duration-150 flex items-center justify-between gap-1.5 overflow-hidden group "
                    + ("bg-[#343a40] border border-[#adb5bd] shadow-sm shadow-black/20" if is_active else "bg-[#343a40]/30 border border-[#495057]/50 hover:bg-[#343a40]/70 hover:border-[#6c757d]")
                )

                with ui.element("div").classes(item_classes) as item_row:
                    with ui.row().classes("items-center gap-2 flex-1 min-w-0 overflow-hidden no-wrap"):
                        ui.icon("chat", size="0.85rem").classes("text-[#f8f9fa] shrink-0" if is_active else "text-[#6c757d] shrink-0")
                        ui.label(title).classes(
                            "text-[11px] leading-tight truncate flex-1 min-w-0 "
                            + ("text-[#f8f9fa] font-semibold" if is_active else "text-[#ced4da] group-hover:text-[#f8f9fa]")
                        )

                    del_btn = ui.button(icon="delete", color=None).props("dense flat round size=xs").classes(
                        "opacity-0 group-hover:opacity-100 text-[#6c757d] hover:text-[#f8f9fa] transition shrink-0"
                    ).tooltip("Delete Session")

                    async def select_fn(sess_id=sid):
                        if sess_id != self.state.current_session_id:
                            await self.on_select_session(sess_id)

                    async def delete_fn(sess_id=sid):
                        success = await self.client.delete_session(sess_id)
                        if success:
                            ui.notify("Session deleted", type="info", position="top-right")
                            await self.refresh_sessions()
                            if self.state.current_session_id == sess_id:
                                remaining = await self.client.fetch_sessions()
                                if remaining:
                                    await self.on_select_session(remaining[0]["id"])
                                else:
                                    await self.on_create_session()

                    item_row.on("click", select_fn)
                    del_btn.on("click.stop", delete_fn)
