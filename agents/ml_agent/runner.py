import asyncio
import base64
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

import pandas as pd

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
PLOTLY_PATTERN = r"<!--\s*PLOTLY_JSON_START\s*-->\s*([\s\S]*?)\s*<!--\s*PLOTLY_JSON_END\s*-->"


def sanitize_code_comments(code: str) -> str:
    """
    Strips out prompt section headers, rule titles, and meta-comments from Python code.
    """
    rule_patterns = [
        r"^\s*#\s*\d+\.\s*(?:Data Ingestion|Adaptive ML|Visualization|Output|Console|Execution|Requirements).*$",
        r"^\s*#\s*(?:Output and Console Printing Rules|Visualization Requirements|Adaptive ML Algorithm Selection|Data Ingestion & Preprocessing|Execution Environment).*$",
        r"^\s*#\s*Requirements for the Python script.*$",
    ]
    lines = []
    for line in code.splitlines():
        if any(re.match(pat, line, re.IGNORECASE) for pat in rule_patterns):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class MLCodeRunner:
    """
    Subprocess execution sandbox that executes generated Python ML scripts
    using a dedicated Python virtual environment and collects stdout, stderr,
    and generated Plotly JSON chart artifacts.
    """

    def __init__(
        self,
        python_bin: str,
        output_dir: Path,
        timeout_seconds: int = 90,
    ) -> None:
        self.python_bin = python_bin
        self.output_dir = output_dir.resolve()
        self.scripts_dir = self.output_dir / "ml_scripts"
        self.timeout_seconds = timeout_seconds

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_images(self) -> Set[Path]:
        """
        Takes a snapshot of existing image files in the output directory.
        """
        if not self.output_dir.exists():
            return set()
        return {
            p
            for p in self.output_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        }

    def _snapshot_json_files(self) -> Dict[Path, float]:
        """
        Takes a snapshot of existing JSON files and their modification times in the output directory.
        """
        if not self.output_dir.exists():
            return {}
        return {
            p: p.stat().st_mtime
            for p in self.output_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".json"
        }

    async def run_code(
        self,
        code: str,
        in_memory_datasets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes Python code in a subprocess, capturing output, errors, and new chart artifacts.
        Pre-loads in-memory datasets into the Python process so scripts can directly copy them.
        Removes all temporary script files from disk upon completion.

        Args:
            code (str): Python script to execute.
            in_memory_datasets (Optional[Dict[str, Any]]): Mapping of variable names to DataFrames/records.

        Returns:
            Dict[str, Any]: Execution status, stdout, stderr, clean code, charts, and plots.
        """
        clean_code = sanitize_code_comments(code)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        start_time = datetime.now().timestamp()
        script_file = self.scripts_dir / f"ml_run_{timestamp}.py"

        # Build in-memory dataset injection preamble if provided
        executable_script_parts = []
        if in_memory_datasets:
            bootstrap_lines = [
                "# --- SYSTEM IN-MEMORY DATASET INJECTION ---",
                "import base64",
                "import json",
                "import pandas as pd",
            ]
            for var_name, data_val in in_memory_datasets.items():
                if isinstance(data_val, pd.DataFrame):
                    raw_json = data_val.to_json(orient="records", date_format="iso")
                elif isinstance(data_val, list):
                    raw_json = json.dumps(data_val, default=str)
                elif isinstance(data_val, str):
                    raw_json = data_val
                else:
                    raw_json = json.dumps(data_val, default=str)

                b64_str = base64.b64encode(raw_json.encode("utf-8")).decode("ascii")
                bootstrap_lines.append(
                    f"{var_name} = pd.DataFrame(json.loads(base64.b64decode(b'{b64_str}').decode('utf-8')))"
                )
            bootstrap_lines.append("# --- END IN-MEMORY INJECTION ---\n")
            executable_script_parts.append("\n".join(bootstrap_lines))

        executable_script_parts.append(clean_code)
        full_executable_code = "\n".join(executable_script_parts)

        # Write script to disk for execution
        script_file.write_text(full_executable_code, encoding="utf-8")

        initial_images = self._snapshot_images()
        initial_jsons = self._snapshot_json_files()

        env = dict(os.environ)
        # Ensure headless operation
        env["MPLBACKEND"] = "Agg"
        env["PYTHONUNBUFFERED"] = "1"
        py_bin_path = Path(self.python_bin)
        if py_bin_path.parent.name in ("bin", "Scripts"):
            env["VIRTUAL_ENV"] = str(py_bin_path.parent.parent)
            env["PATH"] = f"{py_bin_path.parent}:{env.get('PATH', '')}"

        try:
            process = await asyncio.create_subprocess_exec(
                self.python_bin,
                str(script_file),
                cwd=str(self.output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=float(self.timeout_seconds),
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            returncode = process.returncode or 0

            # 1. Detect newly created or updated Plotly JSON charts on disk
            current_jsons = self._snapshot_json_files()
            new_json_paths = [
                p
                for p, mtime in current_jsons.items()
                if p not in initial_jsons or mtime > initial_jsons[p] or mtime >= (start_time - 2.0)
            ]
            new_json_paths = sorted(new_json_paths, key=lambda p: current_jsons[p])

            if not new_json_paths and current_jsons:
                newest = max(current_jsons.keys(), key=lambda p: current_jsons[p])
                if current_jsons[newest] >= (start_time - 600.0):
                    new_json_paths = [newest]

            charts: List[Dict[str, Any]] = []
            for jp in new_json_paths:
                try:
                    spec_content = json.loads(jp.read_text(encoding="utf-8"))
                    if isinstance(spec_content, dict) and ("data" in spec_content or "layout" in spec_content):
                        charts.append({
                            "file_name": jp.name,
                            "spec": spec_content,
                        })
                except Exception as ex:
                    logger.warning(f"Could not parse chart JSON from {jp.name}: {ex}")

            # 2. Fallback: extract Plotly JSON if emitted directly via stdout markers
            if not charts:
                for match in re.finditer(PLOTLY_PATTERN, stdout):
                    spec_str = match.group(1).strip()
                    try:
                        spec_content = json.loads(spec_str)
                        if isinstance(spec_content, dict) and ("data" in spec_content or "layout" in spec_content):
                            charts.append({
                                "file_name": "chart.json",
                                "spec": spec_content,
                            })
                    except Exception as ex:
                        logger.warning(f"Could not parse Plotly chart JSON from stdout: {ex}")

            # 3. Clean stdout by replacing giant JSON blocks and stripping boilerplate phrases
            clean_stdout = re.sub(
                PLOTLY_PATTERN,
                "\n[Interactive Plotly chart returned for database storage]\n",
                stdout,
            ).strip()

            boilerplate_patterns = [
                r"(?i)^\s*task\s+(?:completed|finished|executed)(?:\s+successfully)?\.?\s*$",
                r"(?i)^\s*script\s+(?:completed|finished|executed)(?:\s+successfully)?\.?\s*$",
                r"(?i)^\s*(?:starting|running|executing)\s+.*$",
                r"(?i)^\s*plotly\s+chart\s+successfully\s+saved\s+to:?.*$",
                r"(?i)^\s*figure\s+saved\s+to:?.*$",
                r"(?i)^\s*data\s+loaded\s+successfully\.?\s*$",
                r"(?i)^\s*done\.?\s*$",
            ]
            clean_lines = [
                line for line in clean_stdout.splitlines()
                if not any(re.match(pat, line) for pat in boilerplate_patterns)
            ]
            clean_stdout = re.sub(r"\n{3,}", "\n\n", "\n".join(clean_lines)).strip()

            success = returncode == 0
            return {
                "success": success,
                "returncode": returncode,
                "stdout": clean_stdout,
                "raw_stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "error_trace": stderr.strip() if not success else "",
                "code": clean_code,
                "script_path": str(script_file.resolve()),
                "plots": [],
                "charts": charts,
            }

        except asyncio.TimeoutError:
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
                "script_path": str(script_file.resolve()),
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
                "script_path": str(script_file.resolve()),
                "plots": [],
                "charts": [],
            }
        finally:
            # Immediately delete the script file from disk to ensure zero filesystem residue
            try:
                script_file.unlink(missing_ok=True)
            except Exception as ex:
                logger.debug(f"Could not delete temp script file {script_file.name}: {ex}")
