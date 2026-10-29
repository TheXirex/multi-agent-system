from contextlib import asynccontextmanager
import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from agents.orchestrator import FinalOrchestratorResult, OrchestratorAgent, build_orchestrator
from shared.tools import get_tool_action_label

logger = logging.getLogger("agents.service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("google_genai.models").setLevel(logging.WARNING)

_orchestrator: Optional[OrchestratorAgent] = None


def get_orchestrator() -> OrchestratorAgent:
    """Returns or lazily initializes the shared singleton OrchestratorAgent instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator


class ProcessQueryRequest(BaseModel):
    """Request payload for processing a natural language query through the Orchestrator."""

    query: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    active_metadata: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    trace_id: Optional[str] = None


class ProcessQueryResponse(BaseModel):
    """Response payload returned by the synchronous Orchestrator processing endpoint."""

    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    trace_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initializes the Orchestrator on service startup and logs shutdown."""
    logger.info("Starting AI Multi-Agent Service...")
    get_orchestrator()
    yield
    logger.info("Shutting down AI Multi-Agent Service.")


app = FastAPI(
    title="AI Multi-Agent Service",
    description="Dedicated microservice hosting the AI Orchestrator and MCP domain agents.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Returns service health status."""
    return {"status": "ok", "service": "ai"}


@app.get("/tools")
async def list_tools() -> Dict[str, Any]:
    """Lists all MCP tools exposed by connected domain agents."""
    orchestrator = get_orchestrator()
    async with orchestrator.mcp_manager.open_session() as session:
        tools = await session.list_tools()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "action_label": get_tool_action_label(t.name),
                    "server": t.server_name,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
        }


@app.post("/process", response_model=ProcessQueryResponse)
async def process_query(req: ProcessQueryRequest) -> ProcessQueryResponse:
    """Executes a natural language query through the multi-agent orchestrator."""
    orchestrator = get_orchestrator()
    try:
        result: FinalOrchestratorResult = await orchestrator.process_query(
            query=req.query,
            history=req.history,
            active_metadata=req.active_metadata,
            session_id=req.session_id,
            trace_id=req.trace_id,
        )
        return ProcessQueryResponse(
            response=result.final_response,
            metadata=result.metadata,
            session_id=req.session_id,
            trace_id=result.trace_id or req.trace_id,
        )
    except Exception as exc:
        logger.error(f"Error processing query in AI service: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/process/stream")
async def process_query_stream_endpoint(req: ProcessQueryRequest) -> StreamingResponse:
    """Streams real-time tool action labels and the final structured response over SSE."""
    orchestrator = get_orchestrator()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in orchestrator.process_query_stream(
                query=req.query,
                history=req.history,
                active_metadata=req.active_metadata,
                session_id=req.session_id,
                trace_id=req.trace_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.error(f"Error in process_query_stream: {exc}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def main() -> None:
    """Starts the Uvicorn ASGI server hosting the AI Multi-Agent Service."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("agents.service:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
