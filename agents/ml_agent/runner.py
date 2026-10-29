import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class MLCodeRunner:
    """
    Subprocess execution sandbox that executes generated Python ML scripts
    using a dedicated Python virtual environment and collects stdout, stderr,
    and generated Plotly JSON chart artifacts.
    """

    def __init__(
        self,
        python_bin: str,
        timeout_seconds: int = 90,
    ) -> None:
        """Initializes the ML subprocess code runner."""
        self.python_bin = python_bin
        self.timeout_seconds = timeout_seconds

    def _collect_json_charts(self, directory: Path) -> List[Dict[str, Any]]:
        """Reads and validates all Plotly JSON chart specifications generated in the target directory."""
        if not directory.exists():
            return []

        json_files = sorted(
            (p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".json"),
            key=lambda p: p.stat().st_mtime,
        )

        charts: List[Dict[str, Any]] = []
        for jp in json_files:
            try:
                spec_content = json.loads(jp.read_text(encoding="utf-8"))
                if isinstance(spec_content, dict) and ("data" in spec_content or "layout" in spec_content):
                    charts.append({
                        "file_name": jp.name,
                        "spec": spec_content,
                    })
            except Exception as ex:
                logger.warning(f"Could not parse chart JSON from {jp.name}: {ex}")

        return charts

    async def run_code(
        self,
        code: str,
        in_memory_datasets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes Python code in an ephemeral system temporary directory, capturing output, errors,
        and generated Plotly chart artifacts. Deduplicates in-memory DataFrame aliases during
        bootstrap serialization and automatically cleans up the temporary directory upon exit.

        Args:
            code (str): Python script to execute.
            in_memory_datasets (Optional[Dict[str, Any]]): Mapping of variable names to DataFrames or records.

        Returns:
            Dict[str, Any]: Execution status, returncode, stdout, stderr, clean code, and collected charts.
        """
        clean_code = code.strip()

        # Build in-memory dataset injection preamble with alias deduplication
        executable_script_parts: List[str] = []
        if in_memory_datasets:
            bootstrap_lines = [
                "# --- SYSTEM IN-MEMORY DATASET INJECTION ---",
                "import base64",
                "import json",
                "import pandas as pd",
            ]
            serialized_df_ids: Dict[int, str] = {}

            for var_name, data_val in in_memory_datasets.items():
                obj_id = id(data_val)
                if obj_id in serialized_df_ids:
                    source_var = serialized_df_ids[obj_id]
                    bootstrap_lines.append(f"{var_name} = {source_var}")
                    continue

                if isinstance(data_val, pd.DataFrame):
                    raw_json = data_val.to_json(orient="records", date_format="iso")
                elif isinstance(data_val, str):
                    raw_json = data_val
                else:
                    raw_json = json.dumps(data_val, default=str)

                b64_str = base64.b64encode(raw_json.encode("utf-8")).decode("ascii")
                bootstrap_lines.append(
                    f"{var_name} = pd.DataFrame(json.loads(base64.b64decode(b'{b64_str}').decode('utf-8')))"
                )
                serialized_df_ids[obj_id] = var_name

            bootstrap_lines.append("# --- END IN-MEMORY INJECTION ---\n")
            executable_script_parts.append("\n".join(bootstrap_lines))

        executable_script_parts.append(clean_code)
        full_executable_code = "\n".join(executable_script_parts)

        env = dict(os.environ)
        env["MPLBACKEND"] = "Agg"
        env["PYTHONUNBUFFERED"] = "1"
        py_bin_path = Path(self.python_bin)
        if py_bin_path.parent.name in ("bin", "Scripts"):
            env["VIRTUAL_ENV"] = str(py_bin_path.parent.parent)
            env["PATH"] = f"{py_bin_path.parent}{os.pathsep}{env.get('PATH', '')}"

        with tempfile.TemporaryDirectory(prefix="ml_run_") as tmp_dir:
            run_dir = Path(tmp_dir)
            script_file = run_dir / "ml_script.py"
            script_file.write_text(full_executable_code, encoding="utf-8")

            process: Optional[asyncio.subprocess.Process] = None
            try:
                process = await asyncio.create_subprocess_exec(
                    self.python_bin,
                    str(script_file),
                    cwd=str(run_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=float(self.timeout_seconds),
                )

                stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
                stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
                returncode = process.returncode or 0
                success = returncode == 0

                charts = self._collect_json_charts(run_dir)

                return {
                    "success": success,
                    "returncode": returncode,
                    "stdout": stdout,
                    "raw_stdout": stdout,
                    "stderr": stderr,
                    "error_trace": stderr if not success else "",
                    "code": clean_code,
                    "script_path": str(script_file),
                    "plots": [],
                    "charts": charts,
                }

            except asyncio.TimeoutError:
                if process is not None:
                    try:
                        process.kill()
                    except Exception:
                        pass
                return {
                    "success": False,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"Execution timed out after {self.timeout_seconds} seconds.",
                    "error_trace": f"TimeoutError: Execution exceeded {self.timeout_seconds}s limit.",
                    "code": clean_code,
                    "script_path": str(script_file),
                    "plots": [],
                    "charts": [],
                }
            except Exception as exc:
                return {
                    "success": False,
                    "returncode": -1,
                    "stdout": "",
                    "stderr": str(exc),
                    "error_trace": str(exc),
                    "code": clean_code,
                    "script_path": str(script_file),
                    "plots": [],
                    "charts": [],
                }
