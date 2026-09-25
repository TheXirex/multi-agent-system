import argparse
import json
import os
import sys
from typing import Optional

from agents.db_agent.agent import DBAgent
from agents.db_agent.factory import build_agent


def run_single_query(agent: DBAgent, query_text: str) -> None:
    """
    Runs a single query request through the agent and prints formatted results to stdout.

    Args:
        agent (DBAgent): Initialized DBAgent instance.
        query_text (str): Natural language user request.

    Returns:
        None
    """
    print(f"\n[User Query]: {query_text}")
    result = agent.run(query_text)
    print("\n--- Agent Execution Result ---")
    print(f"Response: {result.get('response')}")
    if result.get("sql_query"):
        print(f"Generated SQL: {result.get('sql_query')}")
    if result.get("tool_result"):
        print(f"Tool Output: {json.dumps(result.get('tool_result'), indent=2, default=str)}")


def main() -> None:
    """
    Entry point for the db-agent service handling CLI arguments or interactive loop.

    Args:
        None

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description="DB Agent for SQL generation and CSV export")
    parser.add_argument("-q", "--query", type=str, help="Natural language query to execute")
    args = parser.parse_args()

    agent = build_agent()

    query = args.query

    if query:
        run_single_query(agent, query)
        return

    if sys.stdin.isatty():
        print("DB Agent started in interactive mode. Type 'exit' or 'quit' to terminate.")
        while True:
            try:
                user_input = input("\nEnter query > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    break
                run_single_query(agent, user_input)
            except (KeyboardInterrupt, EOFError):
                break
    else:
        print("No query provided. Set QUERY environment variable or pass --query argument.")


if __name__ == "__main__":
    main()
