import asyncio
import base64
import logging
import os
import re
from typing import Any, Dict, List, Optional
import warnings

from nicegui import ui

from ui.api_client import DBStudioClient
from ui.components.chat import ChatComponent
from ui.components.header import HeaderComponent
from ui.components.sidebar import SidebarComponent
from ui.components.workspace import WorkspaceComponent
from ui.state import StudioState

warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger("ui.app")


def extract_code_block(text: str, language: str) -> Optional[str]:
    """
    Extracts code snippet for a given language from markdown fenced blocks.
    """
    if not text:
        return None
    pattern = rf"```{language}\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        code = match.group(1).strip()
        if code:
            return code
    return None



def create_ui() -> None:
    """
    Constructs the modular DB Studio UI:
    - Top Header with session title and system indicators
    - Left Sidebar with chat sessions list, active selection, and management
    - Main Center Chat panel with multi-turn memory, Plotly previews, and suggested queries
    - Right Tabbed Workspace for Table Data, Plotly Visualizations, and Scripts
    """
    state = StudioState()
    client = DBStudioClient()

    # Enable dark mode and configure NiceGUI Quasar color palette
    ui.dark_mode().enable()
    ui.colors(
        primary="#343a40",
        secondary="#495057",
        accent="#ced4da",
        dark="#212529",
        dark_page="#212529",
        positive="#adb5bd",
        negative="#495057",
        info="#ced4da",
        warning="#6c757d",
    )

    # Inject global styles for the monochrome palette, responsive layout, and custom components
    ui.add_head_html("""
    <style>
        :root, body, body.body--dark {
            --q-primary: #343a40 !important;
            --q-secondary: #495057 !important;
            --q-accent: #ced4da !important;
            --q-dark: #212529 !important;
            --q-dark-page: #212529 !important;
            --q-info: #ced4da !important;
            --q-positive: #adb5bd !important;
            --q-warning: #6c757d !important;
            --q-negative: #495057 !important;
        }
        * {
            outline-color: #ced4da !important;
        }
        ::selection {
            background-color: #495057 !important;
            color: #f8f9fa !important;
        }
        ::-moz-selection {
            background-color: #495057 !important;
            color: #f8f9fa !important;
        }
        a, a:visited {
            color: #ced4da !important;
            text-decoration-color: #6c757d !important;
        }
        a:hover {
            color: #f8f9fa !important;
        }
        html, body {
            margin: 0;
            padding: 0;
            height: 100vh;
            overflow: hidden;
            background-color: #212529 !important;
            color: #dee2e6;
        }
        .q-drawer {
            background-color: #212529 !important;
        }
        .q-header {
            background-color: #212529 !important;
        }

        /* Quasar text & background overrides */
        .text-primary {
            color: #f8f9fa !important;
        }
        .bg-primary {
            background-color: #343a40 !important;
            color: #f8f9fa !important;
        }
        .text-info {
            color: #ced4da !important;
        }
        .bg-info {
            background-color: #343a40 !important;
            color: #ced4da !important;
        }

        /* Buttons Styling & Text Contrast */
        .q-btn {
            text-transform: none !important;
        }
        .q-btn--standard, .q-btn--unelevated {
            background-color: #343a40 !important;
            color: #f8f9fa !important;
            border: 1px solid #495057 !important;
        }
        .q-btn--standard .q-btn__content,
        .q-btn--standard .q-icon,
        .q-btn--unelevated .q-btn__content,
        .q-btn--unelevated .q-icon {
            color: #f8f9fa !important;
        }
        .q-btn--standard:hover, .q-btn--unelevated:hover {
            background-color: #495057 !important;
            border-color: #6c757d !important;
        }

        /* High-Contrast Light Buttons (.btn-light-accent) */
        .btn-light-accent,
        .btn-light-accent.q-btn,
        .btn-light-accent.q-btn--unelevated,
        .btn-light-accent.q-btn--standard {
            background-color: #f8f9fa !important;
            color: #212529 !important;
            border: 1px solid #dee2e6 !important;
        }
        .btn-light-accent .q-btn__content,
        .btn-light-accent .q-icon,
        .btn-light-accent span,
        .btn-light-accent div {
            color: #212529 !important;
        }
        .btn-light-accent:hover {
            background-color: #dee2e6 !important;
            border-color: #ced4da !important;
        }
        .btn-light-accent:hover .q-btn__content,
        .btn-light-accent:hover .q-icon,
        .btn-light-accent:hover span {
            color: #212529 !important;
        }

        /* Flat Buttons */
        .q-btn--flat {
            background-color: transparent !important;
            border: none !important;
        }
        .q-btn--flat .q-btn__content {
            color: inherit !important;
        }

        /* Quasar Tabs & Indicators */
        .q-tabs {
            color: #adb5bd !important;
        }
        .q-tab {
            color: #adb5bd !important;
        }
        .q-tab--active {
            color: #f8f9fa !important;
        }
        .q-tab--active .q-tab__icon,
        .q-tab--active .q-tab__label {
            color: #f8f9fa !important;
        }
        .q-tab__indicator {
            background: #f8f9fa !important;
            height: 2px !important;
        }

        /* Quasar Fields & Inputs (eliminate blue focus border) */
        .q-field__control {
            color: #ced4da !important;
        }
        .q-field__marginal {
            color: #adb5bd !important;
        }
        .q-field--outlined .q-field__control:before {
            border-color: #495057 !important;
        }
        .q-field--outlined:hover .q-field__control:before {
            border-color: #6c757d !important;
        }
        .q-field--outlined.q-field--focused .q-field__control:after {
            border-color: #ced4da !important;
            border-width: 1px !important;
        }
        .q-field--focused .q-field__native,
        .q-field--focused .q-field__prefix,
        .q-field--focused .q-field__suffix {
            color: #f8f9fa !important;
        }
        .q-field--focused .q-field__label {
            color: #ced4da !important;
        }
        .q-field__native {
            color: #f8f9fa !important;
        }

        /* Quasar Spinners & Ripple */
        .q-spinner {
            color: #ced4da !important;
        }
        .q-ripple {
            color: #ced4da !important;
        }
        .q-focus-helper {
            background: currentColor !important;
            opacity: 0.15 !important;
        }

        /* Quasar Uploader */
        .q-uploader {
            background-color: #343a40 !important;
            border: 1px solid #495057 !important;
            color: #dee2e6 !important;
        }
        .q-uploader__header {
            background-color: #212529 !important;
            color: #f8f9fa !important;
        }
        .q-uploader__header-content {
            color: #f8f9fa !important;
        }
        .q-uploader__title, .q-uploader__subtitle {
            color: #ced4da !important;
        }
        .q-uploader__list {
            background-color: #343a40 !important;
        }
        .q-uploader__file {
            background-color: #212529 !important;
            border: 1px solid #495057 !important;
            color: #dee2e6 !important;
        }

        /* Quasar Notifications */
        .q-notification {
            background-color: #343a40 !important;
            color: #f8f9fa !important;
            border: 1px solid #495057 !important;
        }
        .q-notification__message {
            color: #f8f9fa !important;
        }
        .q-notification__icon {
            color: #ced4da !important;
        }

        /* Quasar Tooltips */
        .q-tooltip {
            background-color: #212529 !important;
            color: #f8f9fa !important;
            border: 1px solid #495057 !important;
            font-size: 11px !important;
        }

        /* Quasar Badges & Expansions */
        .q-badge {
            background-color: #343a40 !important;
            color: #f8f9fa !important;
            border-color: #495057 !important;
        }
        .q-expansion-item__toggle-icon {
            color: #ced4da !important;
        }
        .q-expansion-item--expanded .q-expansion-item__toggle-icon {
            color: #f8f9fa !important;
        }

        /* Quasar Tables */
        .q-table__container {
            background-color: #212529 !important;
            border-color: #495057 !important;
        }
        .q-table thead tr th {
            background-color: #343a40 !important;
            color: #f8f9fa !important;
            font-weight: 600;
            border-bottom: 1px solid #495057 !important;
        }
        .q-table tbody tr {
            background-color: #212529 !important;
            color: #dee2e6 !important;
        }
        .q-table tbody tr:hover {
            background-color: #343a40 !important;
        }
        .q-table tbody td {
            border-bottom: 1px solid rgba(73, 80, 87, 0.5) !important;
        }
        .q-table__bottom {
            background-color: #212529 !important;
            color: #adb5bd !important;
            border-top: 1px solid #495057 !important;
        }
        .q-table__bottom .q-btn {
            color: #ced4da !important;
        }

        /* Markdown Code Blocks */
        pre {
            margin: 0;
            max-width: 100%;
        }
        .q-markdown pre, .q-markdown code {
            background-color: #212529 !important;
            color: #ced4da !important;
            border-color: #495057 !important;
        }
        .q-markdown a {
            color: #ced4da !important;
        }

        /* Scrollbars */
        .q-scrollarea__content {
            width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
        .q-scrollarea__thumb {
            background: #495057 !important;
            opacity: 0.7;
        }
        .q-scrollarea__thumb:hover {
            background: #adb5bd !important;
            opacity: 1;
        }
        .js-plotly-plot, .plot-container {
            max-width: 100% !important;
            width: 100% !important;
        }
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: #212529;
        }
        ::-webkit-scrollbar-thumb {
            background: #495057;
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #adb5bd;
        }
    </style>
    """)

    # Define callbacks before rendering components
    async def switch_to_session(session_id: str) -> None:
        """
        Loads a chat session, restores all message bubbles with inline artifacts,
        and synchronizes the right workspace tabs.
        """
        if state.is_busy:
            return

        detail = await client.get_session_detail(session_id)
        if not detail:
            ui.notify(f"Could not load session {session_id}", type="warning")
            return

        state.current_session_id = session_id
        state.current_session_title = detail.get("title", "New Session")
        header.update_session_title(state.current_session_title)
        state.reset_workspace()

        chat.clear_messages()

        latest_ds_data: Optional[Dict[str, Any]] = None
        latest_charts: List[Dict[str, Any]] = []
        latest_py_script: Optional[str] = None
        latest_sql_query: Optional[str] = None

        messages = detail.get("messages", [])
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            meta = msg.get("metadata") or {}

            if role == "user":
                chat.render_user_message(content, attachments=meta.get("attachments"))
            else:
                ds_id = meta.get("dataset_id")
                ch_id = meta.get("chart_id")
                ch_ids = meta.get("chart_ids") or ([ch_id] if ch_id else [])
                sc_id = meta.get("script_id")

                ds_data = None
                if ds_id:
                    ds_data = await client.fetch_dataset(ds_id)
                    if ds_data:
                        latest_ds_data = ds_data

                charts_data: List[Dict[str, Any]] = []
                for cid in ch_ids:
                    ch_item = await client.fetch_chart(cid)
                    if ch_item:
                        charts_data.append(ch_item)
                if charts_data:
                    latest_charts = charts_data

                py_script = None
                sql_script = ds_data.get("query") if ds_data else None

                if sc_id:
                    sc_item = await client.fetch_script(sc_id)
                    if sc_item and sc_item.get("script"):
                        lang = sc_item.get("language", "python")
                        if lang == "sql":
                            sql_script = sc_item.get("script")
                        else:
                            py_script = sc_item.get("script")

                # Fallback to regex extraction from message markdown content
                if not sql_script:
                    sql_script = extract_code_block(content, "sql")
                if not py_script:
                    py_script = extract_code_block(content, "python")

                if sql_script:
                    latest_sql_query = sql_script
                if py_script:
                    latest_py_script = py_script

                chat.render_assistant_message(
                    response_text=content,
                    metadata=meta,
                    dataset_data=ds_data,
                    charts_data=charts_data,
                    python_script=py_script,
                    sql_query=sql_script,
                )

        # Update right workspace with latest active artifacts
        workspace.update_workspace(
            dataset_data=latest_ds_data,
            charts_data=latest_charts,
            python_script=latest_py_script,
            sql_query=latest_sql_query,
        )

        await sidebar.refresh_sessions()

    async def handle_new_session() -> None:
        """
        Creates and switches to a fresh chat session.
        """
        if state.is_busy:
            return
        new_sess = await client.create_session(title="New Session")
        if new_sess and "id" in new_sess:
            await switch_to_session(new_sess["id"])

    async def handle_send_query(
        query_text: str,
        attached_files: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Executes query with orchestrator agent, binding attached files to the session,
        rendering message turns, and updating workspace.
        """
        if state.is_busy:
            return

        state.is_busy = True
        chat.render_user_message(query_text, attachments=attached_files)
        chat.show_thinking()

        try:
            # Prepare attachments payload
            attachments_payload: List[Dict[str, str]] = []
            if attached_files:
                for att in attached_files:
                    f_bytes = att.get("file_bytes")
                    if f_bytes:
                        b64_content = base64.b64encode(f_bytes).decode("utf-8")
                        attachments_payload.append({
                            "filename": att.get("filename", "dataset.csv"),
                            "content_base64": b64_content,
                        })

            result = await client.send_query(
                query_text=query_text,
                session_id=state.current_session_id,
                attachments=attachments_payload if attachments_payload else None,
            )
            chat.hide_thinking()

            returned_sid = result.get("session_id")
            if returned_sid:
                state.current_session_id = returned_sid

            response_text = result.get("response", "Query completed.")
            metadata = result.get("metadata") or {}

            # Fetch artifacts for assistant response
            ds_data = None
            if metadata.get("dataset_id"):
                ds_data = await client.fetch_dataset(metadata["dataset_id"])

            chart_ids = metadata.get("chart_ids") or ([metadata["chart_id"]] if metadata.get("chart_id") else [])
            charts_data: List[Dict[str, Any]] = []
            for cid in chart_ids:
                ch_item = await client.fetch_chart(cid)
                if ch_item:
                    charts_data.append(ch_item)

            py_script = None
            sql_query = ds_data.get("query") if ds_data else None

            if metadata.get("script_id"):
                sc_item = await client.fetch_script(metadata["script_id"])
                if sc_item and sc_item.get("script"):
                    if sc_item.get("language") == "sql":
                        sql_query = sc_item.get("script")
                    else:
                        py_script = sc_item.get("script")

            # Fallback to regex extraction from response_text
            if not sql_query:
                sql_query = extract_code_block(response_text, "sql")
            if not py_script:
                py_script = extract_code_block(response_text, "python")

            # Sync active artifacts in studio state
            state.current_sql_query = sql_query
            state.current_python_script = py_script
            state.current_charts = charts_data
            if ds_data:
                state.current_dataset_id = ds_data.get("id")
                state.current_dataset_name = ds_data.get("name")
                state.current_dataset_rows = ds_data.get("rows", [])
                state.current_dataset_columns = ds_data.get("columns", [])


            chat.render_assistant_message(
                response_text=response_text,
                metadata=metadata,
                dataset_data=ds_data,
                charts_data=charts_data,
                python_script=py_script,
                sql_query=sql_query,
            )

            # Update workspace
            workspace.update_workspace(
                dataset_data=ds_data,
                charts_data=charts_data,
                python_script=py_script,
                sql_query=sql_query,
            )

            # Sync session title in header and sidebar
            sessions = await client.fetch_sessions()
            for s in sessions:
                if s["id"] == state.current_session_id:
                    state.current_session_title = s.get("title", "Session")
                    header.update_session_title(state.current_session_title)
                    break

            await sidebar.refresh_sessions(sessions)

        except Exception as error:
            chat.hide_thinking()
            ui.notify(f"Query error: {error}", type="negative", position="top-right")
            chat.render_assistant_message(
                response_text=f"### Workflow Execution Error\n\n```\n{error}\n```"
            )
        finally:
            state.is_busy = False

    async def handle_upload_file(file_bytes: bytes, filename: str) -> None:
        """
        Handles uploaded CSV or Excel file: calls backend upload endpoint,
        retrieves created dataset, renders confirmation card, and updates workspace.
        """
        if state.is_busy:
            return

        state.is_busy = True
        try:
            res = await client.upload_file(
                file_bytes=file_bytes,
                filename=filename,
                session_id=state.current_session_id,
            )
            chat.hide_thinking()

            primary_ds_id = res.get("primary_dataset_id")
            msg_markdown = res.get("message", f"File `{filename}` uploaded successfully.")

            ds_data = None
            if primary_ds_id:
                ds_data = await client.fetch_dataset(primary_ds_id)

            if ds_data:
                state.current_dataset_id = ds_data.get("id")
                state.current_dataset_name = ds_data.get("name")
                state.current_dataset_rows = ds_data.get("rows", [])
                state.current_dataset_columns = ds_data.get("columns", [])

            chat.render_assistant_message(
                response_text=msg_markdown,
                metadata={"dataset_id": primary_ds_id},
                dataset_data=ds_data,
            )

            workspace.update_workspace(
                dataset_data=ds_data,
            )

            sessions = await client.fetch_sessions()
            await sidebar.refresh_sessions(sessions)
            ui.notify(f"File '{filename}' successfully uploaded and stored!", type="positive", position="top-right")

        except Exception as error:
            chat.hide_thinking()
            ui.notify(f"File upload error: {error}", type="negative", position="top-right")
            chat.render_assistant_message(
                response_text=f"### File Ingestion Error\n\n```\n{error}\n```"
            )
        finally:
            state.is_busy = False

    # Instantiate UI components
    sidebar = SidebarComponent(
        client=client,
        state=state,
        on_select_session=switch_to_session,
        on_create_session=handle_new_session,
    )

    header = HeaderComponent(
        state=state,
        on_toggle_sidebar=sidebar.toggle,
        on_new_chat=handle_new_session,
    )

    chat = ChatComponent(
        state=state,
        on_send_query=handle_send_query,
        on_upload_file=handle_upload_file,
    )

    workspace = WorkspaceComponent(
        state=state,
    )

    # Render DOM
    header.render()
    sidebar.render()

    # Main Split Content: Chat (Left / 50%) & Workspace (Right / 50%)
    with ui.element("main").classes(
        "w-full px-4 py-3 grid grid-cols-1 lg:grid-cols-2 gap-4 h-[calc(100vh-56px)] max-h-[calc(100vh-56px)] overflow-hidden bg-[#212529]"
    ):
        with ui.column().classes("h-full p-0 flex flex-col min-w-0 overflow-hidden"):
            chat.render()

        with ui.column().classes("h-full p-0 flex flex-col min-w-0 overflow-hidden"):
            workspace.render()

    # Initial session loading on mount
    async def init_session_state() -> None:
        sessions = await client.fetch_sessions()
        if sessions:
            await switch_to_session(sessions[0]["id"])
        else:
            await handle_new_session()

    ui.timer(0.1, init_session_state, once=True)


def main() -> None:
    """
    Main entry point for starting the NiceGUI web server.
    """
    create_ui()
    ui.run(
        title="Multi-Agent Studio",
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,
    )


if __name__ == "__main__" or __name__ == "__mp_main__":
    main()
