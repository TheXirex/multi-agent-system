import argparse
import asyncio
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.factory import build_orchestrator
from agents.orchestrator.models import FinalOrchestratorResult


async def run_query(agent: OrchestratorAgent, query_text: str) -> None:
    """
    Executes a single natural language query through the Orchestrator and prints execution steps.

    Args:
        agent (OrchestratorAgent): Initialized orchestrator agent.
        query_text (str): User natural language instruction.
    """
    print(f"\n=======================================================")
    print(f"[User Query]: {query_text}")
    print(f"=======================================================")

    result: FinalOrchestratorResult = await agent.run(query_text)

    # 1. Planner output
    print("\n--- 1. Planner Output ---")
    print(f"Reasoning: {result.plan.thought}")
    print(f"Planned Steps ({len(result.plan.steps)}):")
    for s in result.plan.steps:
        print(f"  [{s.step_id}] Tool: {s.tool_name} | Args: {json.dumps(s.arguments)} | Desc: {s.description}")

    # 2. Executor output
    print("\n--- 2. Executor Output ---")
    for step_res in result.raw_answer.steps:
        status_icon = "[OK]" if step_res.success else "[FAILED]"
        print(f"  [{step_res.step_id}] {status_icon} Tool '{step_res.tool_name}'")
        if step_res.error:
            print(f"      Error: {step_res.error}")

    # 3. Finalizer output
    print("\n--- 3. Finalizer (User Answer) ---")
    print(result.final_response)

    # 4. Metadata
    if result.metadata:
        print("\n--- Metadata ---")
        if "table" in result.metadata and result.metadata["table"].get("file_name"):
            tbl = result.metadata["table"]
            print(f"CSV File: {tbl.get('file_name')} ({tbl.get('row_count')} rows)")
        if "code" in result.metadata and result.metadata["code"].get("query"):
            print(f"SQL Query: {result.metadata['code'].get('query')}")


async def async_main() -> None:
    """
    Asynchronous CLI main handler.
    """
    parser = argparse.ArgumentParser(description="Multi-Agent Orchestrator CLI")
    parser.add_argument("-q", "--query", type=str, help="Natural language query to orchestrate")
    args = parser.parse_args()

    agent = build_orchestrator()

    if args.query:
        await run_query(agent, args.query)
        return

    print("Multi-Agent Orchestrator (MCP Client) started in interactive mode.")
    print("Type 'exit' or 'quit' to terminate.")

    while True:
        try:
            user_input = input("\nEnter query > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break
            await run_query(agent, user_input)
        except (KeyboardInterrupt, EOFError):
            break


def main() -> None:
    """
    Entry point for CLI execution.
    """
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
