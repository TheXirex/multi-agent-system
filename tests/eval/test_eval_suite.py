import datetime
from pathlib import Path
import sys
from typing import Any, Dict
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.eval.utils import EvaluationRunner, load_scenarios

SPEC_PATH = Path(__file__).parent / "scenarios.yaml"


@pytest.fixture(scope="session")
def eval_runner() -> EvaluationRunner:
    """Provides a configured EvaluationRunner instance and syncs the Langfuse dataset."""
    runner = EvaluationRunner()
    with open(SPEC_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    meta = data.get("metadata", {})
    runner.sync_langfuse_dataset(
        dataset_name=meta.get("dataset_name", "eval_dataset"),
        description=meta.get("suite_name", "Evaluation"),
        scenarios=data.get("scenarios", []),
    )
    return runner


@pytest.fixture(scope="session")
def run_name() -> str:
    """Generates a unique run name for the evaluation session."""
    return f"eval_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"


@pytest.mark.parametrize("scenario", load_scenarios(SPEC_PATH), ids=lambda s: s["id"])
def test_evaluation_scenario(
    scenario: Dict[str, Any],
    eval_runner: EvaluationRunner,
    run_name: str,
) -> None:
    """Executes all turns of a thematic evaluation scenario in a persistent user session."""
    title = scenario.get("title", scenario.get("id", "session"))
    session_id = eval_runner.create_session(title)

    for turn in scenario.get("turns", []):
        turn_id = turn["turn_id"]
        action = turn.get("action", "query")
        if action == "upload":
            actual = eval_runner.execute_upload(session_id, turn["file_path"], user_query=turn.get("user_query"))
        else:
            actual = eval_runner.execute_turn(session_id, turn["user_query"])
        eval_res = eval_runner.evaluate_turn(turn, actual)

        eval_runner.record_langfuse_telemetry(
            trace_id=actual["trace_id"],
            eval_scores=eval_res,
            scenario_id=scenario["id"],
            turn_id=turn_id,
            run_name=run_name,
            session_id=session_id,
        )

        assert eval_res["passed"], (
            f"Scenario '{scenario['id']}' Turn {turn_id} failed: "
            f"routing={eval_res['routing_score']}, "
            f"tools={eval_res['tool_score']} (called={actual['tools_called']}), "
            f"metadata={eval_res['metadata_score']} (keys={list(actual['metadata'].keys())}), "
            f"failures={eval_res['assertion_failures']}"
        )


if __name__ == "__main__":
    args = ["-v", str(Path(__file__))] + sys.argv[1:]
    sys.exit(pytest.main(args))
