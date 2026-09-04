from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

# Render may run this service with its native Python runtime instead of the
# Dockerfile. Make the repository-bundled official engine importable in both
# deployment modes without copying or reimplementing mini-SWE-agent.
_REPOSITORY_SRC = Path(__file__).resolve().parents[1] / "src"
if _REPOSITORY_SRC.is_dir() and str(_REPOSITORY_SRC) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_SRC))

from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.local import LocalEnvironment, _run
from minisweagent.exceptions import Submitted
from minisweagent.models.openrouter_model import OpenRouterModel


DEFAULT_WORK_MODEL = "cohere/north-mini-code:free"
LEGACY_FREE_MODEL = "openrouter/free"

SYSTEM_TEMPLATE = """You are Open Agent Work Mode running the official mini-SWE-agent engine.
You have one tool: bash. Use it to inspect and modify the active repository.
Work directly in the supplied working directory. Read files before editing, make the requested changes across all necessary files, run tests and builds, diagnose failures, fix them, and retest.
Never expose environment variables, credentials, or tokens. Do not modify files outside the workspace.
When the task is complete and verified, run exactly: echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
"""

INSTANCE_TEMPLATE = """Complete this authorized software-engineering task:

{{task}}

The working directory is {{cwd}}. Begin by inspecting the repository. You must make real changes when required, run appropriate tests, and finish with the completion command only after verification."""


class LoggingLocalEnvironment(LocalEnvironment):
    def __init__(self, *, cwd: str, timeout: int, env: dict[str, str], on_event: Callable[[str, str, dict[str, Any] | None], None]):
        super().__init__(cwd=cwd, timeout=timeout, env=env)
        self._on_event = on_event

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        command = str(action.get("command", ""))
        self._on_event("command_started", f"Running: {command}", {"command": command})
        command_cwd = cwd or self.config.cwd or os.getcwd()
        try:
            command_env = dict(os.environ)
            for secret in ("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_1", "OPENROUTER_API_KEY_2", "OPENROUTER_API_KEY_3", "GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY"):
                command_env.pop(secret, None)
            command_env.update(self.config.env)
            result_process = _run(command, command_cwd, command_env, timeout or self.config.timeout)
            result = {"output": result_process.stdout, "returncode": result_process.returncode, "exception_info": ""}
        except Exception as exc:
            raw_output = getattr(exc, "output", None)
            raw_output = raw_output.decode("utf-8", errors="replace") if isinstance(raw_output, bytes) else (raw_output or "")
            result = {"output": raw_output, "returncode": -1, "exception_info": f"An error occurred while executing the command: {exc}"}
        self._on_event(
            "command_finished",
            f"Command exited with {result.get('returncode')}",
            {
                "command": command,
                "returncode": result.get("returncode"),
                "output": str(result.get("output", ""))[-12000:],
                "ok": result.get("returncode") == 0,
            },
        )
        return result


def run_official_agent(
    *,
    workspace: Path,
    task: str,
    model_name: str,
    api_key: str,
    timeout: int,
    step_limit: int,
    on_event: Callable[[str, str, dict[str, Any] | None], None],
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("No OpenRouter API key is configured for Work Mode.")
    if not model_name or model_name == LEGACY_FREE_MODEL:
        if model_name == LEGACY_FREE_MODEL:
            on_event("model_fallback", f"Ignoring legacy {LEGACY_FREE_MODEL}; using {DEFAULT_WORK_MODEL}.", {"configured_model": model_name, "model": DEFAULT_WORK_MODEL})
        model_name = DEFAULT_WORK_MODEL

    # The official model reads OPENROUTER_API_KEY. This assignment is process-local;
    # the key is never placed in the frontend, trajectory, or command environment.
    previous_key = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = api_key
    try:
        safe_env = dict(os.environ)
        for secret in (
            "OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY_1",
            "OPENROUTER_API_KEY_2",
            "OPENROUTER_API_KEY_3",
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
        ):
            safe_env.pop(secret, None)
        env = LoggingLocalEnvironment(cwd=str(workspace), timeout=timeout, env=safe_env, on_event=on_event)
        model = OpenRouterModel(
            model_name=model_name,
            cost_tracking="ignore_errors",
            model_kwargs={"temperature": 0.15, "max_tokens": 2000},
        )
        agent = DefaultAgent(
            model=model,
            env=env,
            system_template=SYSTEM_TEMPLATE,
            instance_template=INSTANCE_TEMPLATE,
            step_limit=step_limit,
            cost_limit=0,
            wall_time_limit_seconds=timeout,
            max_consecutive_format_errors=3,
        )
        on_event("engine_started", "Official mini-SWE-agent started.", {"model": model_name})
        result = agent.run(task=task, cwd=str(workspace))
        on_event("engine_finished", "Official mini-SWE-agent finished.", {"exit_status": result.get("exit_status", "")})
        return result
    except Submitted as exc:
        result = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
        on_event("engine_finished", "Official mini-SWE-agent submitted the completed task.", result)
        return result
    finally:
        if previous_key is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = previous_key
