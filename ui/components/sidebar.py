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
        self.session_count_badge: Optional[ui.badge] = None

    def render(self) -> ui.left_drawer:
        """
        Creates the Left Drawer sidebar with NiceGUI.
        """
        self.drawer = ui.left_drawer(value=True, bordered=True).classes(
            "bg-slate-950/95 border-r border-slate-800 text-slate-200 flex flex-col p-0 w-72 md:w-80 h-full z-20"
        )

        with self.drawer:
            # Top Section: New Chat Action
            with ui.column().classes("w-full p-4 border-b border-slate-800/80 gap-3"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("forum", size="1.2rem").classes("text-indigo-400")
                        ui.label("Chat Sessions").classes("font-bold text-xs uppercase tracking-wider text-slate-300")
                    self.session_count_badge = ui.badge("0", color="slate-800").classes("text-[10px] text-slate-400 font-mono")

                ui.button(
                    "New Chat",
                    icon="add",
                    on_click=self._handle_create_click,
                ).props("unelevated color=indigo-600 no-caps").classes(
                    "w-full text-xs font-semibold py-2 rounded-lg shadow-md shadow-indigo-600/20 hover:brightness-110"
                )

            # Middle Section: Scrollable Sessions List
            with ui.scroll_area().classes("flex-1 px-3 py-3 overflow-y-auto"):
                self.sessions_list_container = ui.column().classes("w-full gap-2")

            # Bottom Section: Environment / System Info Footer
            with ui.column().classes("w-full p-3 border-t border-slate-800/80 bg-slate-950 gap-1.5"):
                with ui.row().classes("w-full justify-between items-center text-[10px] text-slate-500 font-mono"):
                    ui.label("PostgreSQL Database")
                    ui.badge("Connected", color="emerald-950").classes("text-emerald-400 text-[9px] border border-emerald-800/40")
                with ui.row().classes("w-full justify-between items-center text-[10px] text-slate-500 font-mono"):
                    ui.label("AI Orchestrator")
                    ui.badge("Active", color="indigo-950").classes("text-indigo-400 text-[9px] border border-indigo-800/40")

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

        if self.session_count_badge:
            self.session_count_badge.text = str(len(sessions))

        if not self.sessions_list_container:
            return

        self.sessions_list_container.clear()

        if not sessions:
            with self.sessions_list_container:
                with ui.card().classes("w-full bg-slate-900/40 border border-dashed border-slate-800 p-6 text-center items-center rounded-xl"):
                    ui.icon("chat_bubble_outline", size="2rem").classes("text-slate-600 mb-1")
                    ui.label("No conversations yet").classes("text-xs text-slate-400 font-medium")
                    ui.label("Click '+ New Chat' to start").classes("text-[10px] text-slate-500")
            return

        with self.sessions_list_container:
            for s in sessions:
                sid = s.get("id", "")
                title = s.get("title", "New Session")
                msg_count = s.get("message_count", 0)
                updated_at = s.get("updated_at", "")[:10]
                is_active = (sid == self.state.current_session_id)

                card_classes = (
                    "w-full p-2.5 rounded-lg cursor-pointer transition-all duration-150 group "
                    + ("bg-indigo-950/50 border border-indigo-500/70 shadow-sm" if is_active else "bg-slate-900/60 border border-slate-800/80 hover:bg-slate-850 hover:border-slate-700")
                )

                with ui.card().classes(card_classes):
                    with ui.row().classes("w-full items-center justify-between no-wrap gap-1"):
                        # Session Title & Active Indicator
                        with ui.row().classes("items-center gap-2 flex-1 min-w-0"):
                            ui.icon("chat", size="0.9rem").classes("text-indigo-400" if is_active else "text-slate-500")
                            session_lbl = ui.label(title).classes(
                                "text-xs font-medium truncate flex-1 "
                                + ("text-indigo-200 font-semibold" if is_active else "text-slate-300 group-hover:text-white")
                            )

                        # Delete Action Button
                        del_btn = ui.button(icon="delete").props("dense flat round color=slate-500 size=xs").classes(
                            "opacity-0 group-hover:opacity-100 hover:text-rose-400 transition"
                        ).tooltip("Delete Session")

                    with ui.row().classes("w-full items-center justify-between pt-1 text-[10px] text-slate-500"):
                        ui.label(f"{msg_count} message{'s' if msg_count != 1 else ''}").classes("font-mono")
                        ui.label(updated_at).classes("font-mono")

                    # Event bindings: clicking card selects session, clicking delete deletes
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

                    session_lbl.on("click", select_fn)
                    del_btn.on("click", delete_fn)
