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

    # Enable dark mode
    ui.dark_mode().enable()

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

    # Main Split Content: Chat (Left / 5 cols) & Workspace (Right / 7 cols)
    with ui.element("main").classes(
        "w-full px-5 py-4 grid grid-cols-1 lg:grid-cols-12 gap-5 h-[calc(100vh-68px)]"
    ):
        with ui.column().classes("lg:col-span-5 h-full p-0 flex flex-col min-w-0"):
            chat.render()

        with ui.column().classes("lg:col-span-7 h-full p-0 flex flex-col min-w-0"):
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
