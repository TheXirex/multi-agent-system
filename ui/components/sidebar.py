import asyncio
from typing import Any, Callable, Dict, List, Optional
from nicegui import ui
from ui.api_client import DBStudioClient
from ui.state import StudioState


class SidebarComponent:
    """
    Renders left drawer sidebar dedicated to chat sessions management:
    listing all sessions, highlighting active session, starting new session,
    renaming sessions, and deleting sessions.
    """

    def __init__(
        self,
        client: DBStudioClient,
        state: StudioState,
        on_select_session: Callable[[str], Any],
        on_create_session: Callable[[], Any],
        on_rename_session: Optional[Callable[[str, str], Any]] = None,
    ) -> None:
        self.client = client
        self.state = state
        self.on_select_session = on_select_session
        self.on_create_session = on_create_session
        self.on_rename_session = on_rename_session

        self.drawer: Optional[ui.left_drawer] = None
        self.sessions_list_container: Optional[ui.column] = None

        # Rename Session Dialog
        self.rename_dialog: Optional[ui.dialog] = None
        self.rename_input: Optional[ui.input] = None
        self.rename_target_session_id: Optional[str] = None

    def render(self) -> ui.left_drawer:
        """
        Creates the Left Drawer sidebar with NiceGUI.
        """
        # Rename session modal dialog
        with ui.dialog() as self.rename_dialog, ui.card().classes(
            "bg-[#343a40] border border-[#495057] p-5 rounded-[6px] space-y-4 max-w-sm w-full shadow-2xl"
        ):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("edit", size="sm").classes("text-[#ced4da]")
                    ui.label("Rename Chat Session").classes("font-semibold text-sm text-[#f8f9fa]")
                ui.button(icon="close", color=None, on_click=self.rename_dialog.close).props("flat dense size=xs").classes("text-[#adb5bd] hover:text-[#f8f9fa]")

            self.rename_input = ui.input(
                label="Session Title",
                placeholder="Enter conversation title...",
            ).props("outlined dense color=white autofocus").classes("w-full text-sm bg-[#212529] text-[#f8f9fa]")

            with ui.row().classes("w-full justify-end gap-2 pt-2"):
                ui.button("Cancel", color=None, on_click=self.rename_dialog.close).props("flat dense").classes("text-[#ced4da] hover:text-[#f8f9fa]")
                ui.button("Save", color=None, on_click=self._submit_rename).props("unelevated dense").classes("btn-light-accent font-semibold px-4")

            self.rename_input.on("keydown.enter", self._submit_rename)

        self.drawer = ui.left_drawer(value=True, bordered=True).props("width=280").classes(
            "bg-[#212529] border-r border-[#495057]/60 text-[#dee2e6] flex flex-col p-0 h-full z-20 overflow-hidden"
        )

        with self.drawer:
            # Top Section: New Chat Action (Elevated, no + icon)
            with ui.column().classes("w-full px-3 py-2 border-b border-[#495057]/60 gap-1.5 shrink-0"):
                with ui.row().classes("w-full items-center gap-1.5"):
                    ui.icon("forum", size="0.95rem").classes("text-[#adb5bd]")
                    ui.label("Chat Sessions").classes("font-bold text-[11px] uppercase tracking-wider text-[#ced4da]")

                ui.button(
                    "New Chat",
                    color=None,
                    on_click=self._handle_create_click,
                ).props("unelevated no-caps").classes(
                    "w-full h-8 rounded-[6px] btn-light-accent shadow-sm transition-all text-xs font-bold tracking-wide cursor-pointer flex items-center justify-center p-0"
                )

            # Middle Section: Scrollable Sessions List (directly under divider)
            with ui.scroll_area().classes("flex-1 w-full px-2.5 pt-1.5 pb-2 overflow-x-hidden"):
                self.sessions_list_container = ui.column().classes("w-full gap-1 p-0 m-0 max-w-full overflow-hidden")

        return self.drawer

    def toggle(self) -> None:
        """
        Toggles sidebar drawer visibility.
        """
        if self.drawer:
            self.drawer.toggle()

    def open_rename_dialog(self, session_id: str, current_title: str) -> None:
        """
        Opens the session rename dialog pre-filled with the current title.
        """
        self.rename_target_session_id = session_id
        if self.rename_input:
            self.rename_input.value = current_title
        if self.rename_dialog:
            self.rename_dialog.open()

    async def _submit_rename(self) -> None:
        """
        Submits the session rename to the dedicated backend endpoint.
        """
        if not self.rename_target_session_id or not self.rename_input:
            return

        new_title = (self.rename_input.value or "").strip()
        if not new_title:
            ui.notify("Session title cannot be empty", type="warning", position="top-right")
            return

        target_sid = self.rename_target_session_id
        if self.rename_dialog:
            self.rename_dialog.close()

        success = await self.client.update_session_title(target_sid, new_title)
        if success:
            ui.notify("Session renamed", type="info", position="top-right")
            if self.on_rename_session:
                await self.on_rename_session(target_sid, new_title)
            await self.refresh_sessions()
        else:
            ui.notify("Failed to rename session", type="negative", position="top-right")

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
                with ui.card().classes("w-full max-w-full bg-[#343a40]/50 border border-dashed border-[#495057]/70 p-6 text-center items-center rounded-[6px]"):
                    ui.icon("chat_bubble_outline", size="2rem").classes("text-[#6c757d] mb-1")
                    ui.label("No conversations yet").classes("text-xs text-[#ced4da] font-medium")
                    ui.label("Click 'New Chat' to start").classes("text-[10px] text-[#adb5bd]")
            return

        with self.sessions_list_container:
            for s in sessions:
                sid = s.get("id", "")
                title = s.get("title", "New Session")
                is_active = (sid == self.state.current_session_id)

                item_classes = (
                    "w-full max-w-full box-border px-2.5 py-1.5 rounded-[6px] cursor-pointer transition-all duration-150 flex items-center justify-between gap-1.5 overflow-hidden group "
                    + ("bg-[#343a40] border border-[#adb5bd] shadow-sm shadow-black/20" if is_active else "bg-[#343a40]/30 border border-[#495057]/50 hover:bg-[#343a40]/70 hover:border-[#6c757d]")
                )

                with ui.element("div").classes(item_classes) as item_row:
                    with ui.row().classes("items-center gap-2 flex-1 min-w-0 overflow-hidden no-wrap"):
                        ui.icon("chat", size="0.85rem").classes("text-[#f8f9fa] shrink-0" if is_active else "text-[#6c757d] shrink-0")
                        ui.label(title).classes(
                            "text-[11px] leading-tight truncate flex-1 min-w-0 "
                            + ("text-[#f8f9fa] font-semibold" if is_active else "text-[#ced4da] group-hover:text-[#f8f9fa]")
                        )

                    # Action buttons: Rename and Delete
                    with ui.row().classes("items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition"):
                        edit_btn = ui.button(icon="edit", color=None).props("dense flat size=xs").classes(
                            "text-[#6c757d] hover:text-[#f8f9fa] transition rounded-[6px]"
                        ).tooltip("Rename Session")

                        del_btn = ui.button(icon="delete", color=None).props("dense flat size=xs").classes(
                            "text-[#6c757d] hover:text-[#f8f9fa] transition rounded-[6px]"
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
                    edit_btn.on("click.stop", lambda sess_id=sid, cur_t=title: self.open_rename_dialog(sess_id, cur_t))
                    del_btn.on("click.stop", delete_fn)
