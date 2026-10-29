import logging
import os
import sys
import types
from typing import Any, Optional

logger = logging.getLogger(__name__)

_langfuse_instance: Optional[object] = None
_initialized = False


def ensure_langchain_compatibility_shim() -> None:
    """
    Provides backwards compatibility for Langfuse 2.60.x which imports from
    langchain.callbacks.base and langchain.schema, relocated to langchain_core in LangChain 0.3+.
    """
    try:
        import langchain_core.agents
        import langchain_core.callbacks.base
        import langchain_core.documents

        if "langchain.callbacks" not in sys.modules:
            m_cb = types.ModuleType("langchain.callbacks")
            m_cb_base = types.ModuleType("langchain.callbacks.base")
            m_cb_base.BaseCallbackHandler = langchain_core.callbacks.base.BaseCallbackHandler
            m_cb.base = m_cb_base
            sys.modules["langchain.callbacks"] = m_cb
            sys.modules["langchain.callbacks.base"] = m_cb_base

        if "langchain.schema" not in sys.modules:
            m_sc = types.ModuleType("langchain.schema")
            m_sc_agent = types.ModuleType("langchain.schema.agent")
            m_sc_agent.AgentAction = langchain_core.agents.AgentAction
            m_sc_agent.AgentFinish = langchain_core.agents.AgentFinish
            m_sc_doc = types.ModuleType("langchain.schema.document")
            m_sc_doc.Document = langchain_core.documents.Document
            sys.modules["langchain.schema"] = m_sc
            sys.modules["langchain.schema.agent"] = m_sc_agent
            sys.modules["langchain.schema.document"] = m_sc_doc

        import langfuse.callback
        import langfuse.callback.langchain

        class CleanLangchainCallbackHandler(langfuse.callback.langchain.LangchainCallbackHandler):
            """
            Custom CallbackHandler that bypasses intermediate structural framework spans
            (such as RunnableSequence, PydanticOutputParser, StrOutputParser) to keep
            Langfuse execution trees flat and clean.
            """

            IGNORED_CHAINS = {
                "RunnableSequence",
                "PydanticOutputParser",
                "StrOutputParser",
                "JsonOutputParser",
                "PromptTemplate",
                "ChatPromptTemplate",
            }

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                """Initializes the clean callback handler."""
                super().__init__(*args, **kwargs)
                self._bypassed = set()

            def on_chain_start(
                self,
                serialized: Any,
                inputs: Any,
                *,
                run_id: Any,
                parent_run_id: Optional[Any] = None,
                tags: Optional[Any] = None,
                metadata: Optional[Any] = None,
                **kwargs: Any,
            ) -> Any:
                """Intercepts chain start events to bypass noisy intermediate LangChain wrapper spans."""
                name = self.get_langchain_run_name(serialized, **kwargs)
                if name in self.IGNORED_CHAINS:
                    self._bypassed.add(run_id)
                    target = self.runs.get(parent_run_id) or self.root_span or self.trace
                    if target is not None:
                        self.runs[run_id] = target
                    return None
                return super().on_chain_start(
                    serialized,
                    inputs,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    tags=tags,
                    metadata=metadata,
                    **kwargs,
                )

            def on_chain_end(
                self,
                outputs: Any,
                *,
                run_id: Any,
                parent_run_id: Optional[Any] = None,
                **kwargs: Any,
            ) -> Any:
                """Intercepts chain end events and cleans up bypassed wrapper run mappings."""
                if run_id in self._bypassed:
                    self._bypassed.discard(run_id)
                    self.runs.pop(run_id, None)
                    return None
                return super().on_chain_end(outputs, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

            def on_chain_error(
                self,
                error: Any,
                *,
                run_id: Any,
                parent_run_id: Optional[Any] = None,
                **kwargs: Any,
            ) -> Any:
                """Intercepts chain error events and cleans up bypassed wrapper run mappings."""
                if run_id in self._bypassed:
                    self._bypassed.discard(run_id)
                    self.runs.pop(run_id, None)
                    return None
                return super().on_chain_error(error, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

        langfuse.callback.CallbackHandler = CleanLangchainCallbackHandler
        langfuse.callback.langchain.LangchainCallbackHandler = CleanLangchainCallbackHandler
    except Exception as exc:
        logger.debug(f"LangChain compatibility shim skipped: {exc}")


def get_langfuse() -> Optional[object]:
    """Returns the singleton Langfuse client instance if configured and available, or None on fallback."""
    global _langfuse_instance, _initialized
    if _initialized:
        return _langfuse_instance

    _initialized = True
    ensure_langchain_compatibility_shim()

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-multi-agent-system")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-multi-agent-system")
    host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    enabled_env = os.getenv("LANGFUSE_ENABLED", "true").lower()

    if enabled_env in ("false", "0", "no", "off"):
        logger.info("Langfuse observability is explicitly disabled via LANGFUSE_ENABLED=false.")
        return None

    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        _langfuse_instance = client
        logger.info(f"Langfuse observability client initialized successfully (host={host}).")
        return _langfuse_instance
    except Exception as exc:
        logger.warning(f"Failed to initialize Langfuse client ({exc}). Tracing will be disabled.")
        _langfuse_instance = None
        return None


def is_langfuse_available() -> bool:
    """Checks if the Langfuse client is initialized and operational."""
    client = get_langfuse()
    return client is not None


def flush_langfuse() -> None:
    """Flushes queued telemetry events to the Langfuse backend."""
    client = get_langfuse()
    if client is not None:
        try:
            client.flush()
        except Exception as exc:
            logger.debug(f"Error flushing Langfuse client: {exc}")
