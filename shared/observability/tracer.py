from contextlib import contextmanager
import logging
from typing import Any, Dict, Iterator, List, Optional

from shared.observability.client import ensure_langchain_compatibility_shim, get_langfuse

logger = logging.getLogger(__name__)


class DummySpan:
    """
    Fallback no-op span for environments where Langfuse is not enabled or unreachable.
    """

    def __init__(self, name: str = "dummy", id: str = "dummy-id", trace_id: str = "dummy-trace-id") -> None:
        self.name = name
        self.id = id
        self.trace_id = trace_id

    def update(self, *args: Any, **kwargs: Any) -> "DummySpan":
        return self

    def end(self, *args: Any, **kwargs: Any) -> "DummySpan":
        return self

    def span(self, *args: Any, **kwargs: Any) -> "DummySpan":
        return DummySpan()

    def generation(self, *args: Any, **kwargs: Any) -> "DummySpan":
        return DummySpan()

    def event(self, *args: Any, **kwargs: Any) -> "DummySpan":
        return DummySpan()

    def get_langchain_handler(self, *args: Any, **kwargs: Any) -> Optional[Any]:
        return None


class DummyTrace(DummySpan):
    """
    Fallback no-op trace.
    """
    pass


def get_langfuse_callback_handler(
    trace_name: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """
    Creates and returns a Langfuse CallbackHandler for LangChain and LangGraph runnables.
    """
    client = get_langfuse()
    if client is None:
        return None

    ensure_langchain_compatibility_shim()
    try:
        from langfuse.callback import CallbackHandler

        kwargs: Dict[str, Any] = {
            "stateful_client": client,
        }
        if session_id:
            kwargs["session_id"] = session_id
        if user_id:
            kwargs["user_id"] = user_id
        if trace_name:
            kwargs["trace_name"] = trace_name
        if tags:
            kwargs["tags"] = tags
        if metadata:
            kwargs["metadata"] = metadata

        return CallbackHandler(**kwargs)
    except Exception as exc:
        logger.debug(f"Failed to create Langfuse CallbackHandler: {exc}")
        return None


def create_trace(
    name: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    input_data: Any = None,
    output_data: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    trace_id: Optional[str] = None,
) -> Any:
    """
    Creates a new root trace in Langfuse.
    """
    client = get_langfuse()
    if client is None:
        return DummyTrace(name=name, id=trace_id or "dummy-id", trace_id=trace_id or "dummy-trace-id")

    try:
        trace_kwargs: Dict[str, Any] = {"name": name}
        if trace_id:
            trace_kwargs["id"] = trace_id
        if session_id:
            trace_kwargs["session_id"] = session_id
        if user_id:
            trace_kwargs["user_id"] = user_id
        if input_data is not None:
            trace_kwargs["input"] = input_data
        if output_data is not None:
            trace_kwargs["output"] = output_data
        if metadata is not None:
            trace_kwargs["metadata"] = metadata
        if tags is not None:
            trace_kwargs["tags"] = tags

        return client.trace(**trace_kwargs)
    except Exception as exc:
        logger.debug(f"Error creating Langfuse trace '{name}': {exc}")
        return DummyTrace(name=name, id=trace_id or "dummy-id", trace_id=trace_id or "dummy-trace-id")


@contextmanager
def trace_span(
    name: str,
    parent: Optional[Any] = None,
    trace_id: Optional[str] = None,
    parent_observation_id: Optional[str] = None,
    input_data: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    level: str = "DEFAULT",
) -> Iterator[Any]:
    """
    Context manager that wraps execution in a Langfuse span.
    Supports nesting under a parent span/trace or attaching to an existing trace_id
    and parent_observation_id across distributed agent calls.
    Captures input, output, errors, and metadata transitions.
    """
    span_obj = None
    try:
        if parent is not None and hasattr(parent, "span"):
            span_kwargs: Dict[str, Any] = {"name": name, "level": level}
            if input_data is not None:
                span_kwargs["input"] = input_data
            if metadata is not None:
                span_kwargs["metadata"] = metadata
            span_obj = parent.span(**span_kwargs)
        else:
            client = get_langfuse()
            if client is not None:
                span_kwargs = {"name": name, "level": level}
                if trace_id:
                    span_kwargs["trace_id"] = trace_id
                if parent_observation_id:
                    span_kwargs["parent_observation_id"] = parent_observation_id
                if input_data is not None:
                    span_kwargs["input"] = input_data
                if metadata is not None:
                    span_kwargs["metadata"] = metadata
                span_obj = client.span(**span_kwargs)
    except Exception as exc:
        logger.debug(f"Error creating span '{name}': {exc}")
        span_obj = None

    if span_obj is None:
        span_obj = DummySpan(name=name, trace_id=trace_id or "dummy-trace-id")

    try:
        yield span_obj
    except Exception as exc:
        try:
            span_obj.update(
                level="ERROR",
                status_message=str(exc),
            )
        except Exception:
            pass
        raise
    finally:
        try:
            span_obj.end()
        except Exception:
            pass
