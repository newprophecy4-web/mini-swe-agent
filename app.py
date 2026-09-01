"""
OPEN AGENT
Manus-style autonomous software engineering backend.

Features:
- ChatGPT-like Chat Mode
- Plan Mode
- Finalize Plan
- Authorized Work Mode
- GitHub repository clone/read/search/edit
- Multi-file editing
- Workspace terminal
- Project detection
- Automatic testing
- Build/typecheck
- Error -> diagnosis -> fix -> retest loop
- Git status/diff
- Branch creation
- Commit
- Push
- ZIP project upload/download
- Session status/logs
- Mobile/frontend friendly JSON API

Environment variables:
    GEMINI_API_KEY
    GITHUB_TOKEN
    GEMINI_MODEL
    AUTO_PUSH
    WORKSPACE_ROOT
    MAX_AGENT_ITERATIONS
    MAX_TEST_ITERATIONS
    COMMAND_TIMEOUT
    MAX_FILE_SIZE
    MAX_COMMAND_OUTPUT
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pydantic import BaseModel, Field


# ============================================================
# OPTIONAL GEMINI SDK
# ============================================================

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# ============================================================
# CONFIG
# ============================================================

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO")
)

log = logging.getLogger("open-agent")


BASE_DIR = Path(
    os.getenv("WORKSPACE_ROOT", "/tmp/open-agent")
).resolve()

BASE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)


MAX_AGENT_ITERATIONS = int(
    os.getenv("MAX_AGENT_ITERATIONS", "30")
)


MAX_TEST_ITERATIONS = int(
    os.getenv("MAX_TEST_ITERATIONS", "8")
)


COMMAND_TIMEOUT = int(
    os.getenv("COMMAND_TIMEOUT", "180")
)


MAX_FILE_SIZE = int(
    os.getenv("MAX_FILE_SIZE", "3000000")
)


MAX_COMMAND_OUTPUT = int(
    os.getenv("MAX_COMMAND_OUTPUT", "150000")
)


WORKSPACE_TIMEOUT = int(
    os.getenv("WORKSPACE_TIMEOUT", "1800")
)


AUTO_PUSH = (
    os.getenv("AUTO_PUSH", "false").lower()
    == "true"
)


# ============================================================
# SECURITY / FILE RULES
# ============================================================

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".cache",
    "coverage",
}


SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}


SENSITIVE_PARTS = (
    ".pem",
    ".key",
    "password",
    "secret",
    "credential",
)


# ============================================================
# UTILITIES
# ============================================================

def now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def redact(value: str) -> str:
    """
    Never expose configured secrets in logs/API responses.
    """

    if not isinstance(value, str):
        return value

    for secret in (
        os.getenv("GITHUB_TOKEN"),
        os.getenv("GEMINI_API_KEY"),
    ):
        if secret:
            value = value.replace(
                secret,
                "[REDACTED]"
            )

    return value


def api_error(
    code: str,
    message: str,
    status: int = 400,
) -> HTTPException:

    return HTTPException(
        status_code=status,
        detail={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
    )


def safe_path(
    root: Path,
    relative: str,
    allow_root: bool = False,
) -> Path:

    if not relative:
        raise api_error(
            "INVALID_FILE_PATH",
            "File path is required.",
        )

    if "\x00" in relative:
        raise api_error(
            "INVALID_FILE_PATH",
            "Invalid null byte in path.",
        )

    root = root.resolve()

    candidate = (
        root / relative
    ).resolve()

    try:
        candidate.relative_to(root)

    except ValueError:
        raise api_error(
            "INVALID_FILE_PATH",
            "Path must stay inside workspace.",
        )

    if (
        not allow_root
        and candidate == root
    ):
        raise api_error(
            "INVALID_FILE_PATH",
            "Repository root cannot be used as a file.",
        )

    return candidate


def is_sensitive(path: str | Path) -> bool:

    parts = [
        p.lower()
        for p in Path(path).parts
    ]

    if not parts:
        return False

    name = parts[-1]

    if name in SENSITIVE_NAMES:
        return True

    for part in parts:

        if any(
            marker in part
            for marker in SENSITIVE_PARTS
        ):
            return True

    return False


# ============================================================
# PROCESS EXECUTION
# ============================================================

def run_process(
    command: list[str],
    cwd: Path,
    timeout: int = COMMAND_TIMEOUT,
) -> dict[str, Any]:

    started = time.monotonic()

    command = [
        str(x)
        for x in command
    ]

    try:

        process = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )

        stdout = (
            process.stdout or ""
        )[-MAX_COMMAND_OUTPUT:]

        stderr = (
            process.stderr or ""
        )[-MAX_COMMAND_OUTPUT:]

        return {
            "command": command,
            "stdout": redact(stdout),
            "stderr": redact(stderr),
            "exit_code": process.returncode,
            "duration_ms": int(
                (time.monotonic() - started)
                * 1000
            ),
            "success": process.returncode == 0,
        }

    except subprocess.TimeoutExpired:

        return {
            "command": command,
            "stdout": "",
            "stderr": "Command timed out.",
            "exit_code": -1,
            "duration_ms": int(
                (time.monotonic() - started)
                * 1000
            ),
            "success": False,
            "timed_out": True,
        }

    except FileNotFoundError:

        return {
            "command": command,
            "stdout": "",
            "stderr": (
                f"Executable not found: {command[0]}"
            ),
            "exit_code": 127,
            "duration_ms": int(
                (time.monotonic() - started)
                * 1000
            ),
            "success": False,
        }


# ============================================================
# TERMINAL
# ============================================================

def run_terminal(
    root: Path,
    command: str,
    timeout: int | None = None,
) -> dict[str, Any]:

    command = command.strip()

    if not command:
        raise ValueError(
            "Terminal command is empty."
        )

    timeout = timeout or COMMAND_TIMEOUT

    # The agent receives a real workspace terminal.
    # Commands are executed with cwd=root.
    #
    # Never place secrets in the command.
    #
    # The output is redacted before returning.

    result = subprocess.run(
        command,
        cwd=str(root),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )

    return {
        "command": command,
        "stdout": redact(
            (result.stdout or "")
            [-MAX_COMMAND_OUTPUT:]
        ),
        "stderr": redact(
            (result.stderr or "")
            [-MAX_COMMAND_OUTPUT:]
        ),
        "exit_code": result.returncode,
        "success": result.returncode == 0,
    }


# ============================================================
# GITHUB
# ============================================================

def parse_github(
    url: str,
) -> tuple[str, str]:

    parsed = urlparse(url)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        raise api_error(
            "INVALID_GITHUB_URL",
            "Invalid GitHub URL.",
        )

    if parsed.netloc.lower() != "github.com":
        raise api_error(
            "INVALID_GITHUB_URL",
            "Only github.com repositories are supported.",
        )

    parts = [
        p
        for p in parsed.path.strip("/").split("/")
        if p
    ]

    if len(parts) != 2:
        raise api_error(
            "INVALID_GITHUB_URL",
            "Use https://github.com/owner/repository.git",
        )

    owner = parts[0]

    repository = parts[1]

    if repository.endswith(".git"):
        repository = repository[:-4]

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+",
        owner,
    ):
        raise api_error(
            "INVALID_GITHUB_URL",
            "Invalid repository owner.",
        )

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+",
        repository,
    ):
        raise api_error(
            "INVALID_GITHUB_URL",
            "Invalid repository name.",
        )

    return owner, repository


def github_env() -> dict[str, str]:

    env = os.environ.copy()

    token = env.get(
        "GITHUB_TOKEN"
    )

    if token:

        env["GIT_CONFIG_COUNT"] = "1"

        env["GIT_CONFIG_KEY_0"] = (
            "http.https://github.com/.extraheader"
        )

        env["GIT_CONFIG_VALUE_0"] = (
            f"AUTHORIZATION: bearer {token}"
        )

    return env


def clone_repo(
    repo_url: str,
    destination: Path,
) -> dict[str, Any]:

    owner, name = parse_github(
        repo_url
    )

    token = os.getenv(
        "GITHUB_TOKEN"
    )

    if not token:
        raise api_error(
            "GITHUB_TOKEN_MISSING",
            "GITHUB_TOKEN is not configured.",
            503,
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            repo_url,
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT,
        env=github_env(),
    )

    if result.returncode != 0:

        message = redact(
            result.stderr or
            result.stdout or
            "Git clone failed."
        )

        raise api_error(
            "GITHUB_CLONE_FAILED",
            message[-3000:],
            400,
        )

    branch = run_process(
        [
            "git",
            "branch",
            "--show-current",
        ],
        destination,
    )

    commit = run_process(
        [
            "git",
            "rev-parse",
            "HEAD",
        ],
        destination,
    )

    return {
        "owner": owner,
        "name": name,
        "url": repo_url,
        "branch": (
            branch["stdout"].strip()
            or "HEAD"
        ),
        "commit": (
            commit["stdout"].strip()
        ),
    }


# ============================================================
# FILE SYSTEM
# ============================================================

def list_tree(
    root: Path,
    limit: int = 3000,
) -> list[str]:

    if not root.exists():
        return []

    result = []

    for path in sorted(
        root.rglob("*")
    ):

        relative = path.relative_to(
            root
        )

        if any(
            part in IGNORED_DIRS
            for part in relative.parts
        ):
            continue

        result.append(
            str(relative)
        )

        if len(result) >= limit:
            break

    return result


def read_file(
    root: Path,
    relative: str,
) -> str:

    path = safe_path(
        root,
        relative,
    )

    if is_sensitive(path):
        raise ValueError(
            "Sensitive files cannot be read."
        )

    if not path.is_file():
        raise ValueError(
            "File not found."
        )

    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(
            "File is too large."
        )

    return path.read_text(
        errors="replace"
    )


def write_file(
    root: Path,
    relative: str,
    content: str,
) -> dict[str, Any]:

    if not isinstance(
        content,
        str,
    ):
        raise ValueError(
            "File content must be text."
        )

    if len(
        content.encode("utf-8")
    ) > MAX_FILE_SIZE:

        raise ValueError(
            "File exceeds size limit."
        )

    path = safe_path(
        root,
        relative,
    )

    if path.name == ".git":
        raise ValueError(
            "Protected path."
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary = tempfile.mkstemp(
        prefix=".open-agent-",
        dir=str(path.parent),
    )

    os.close(fd)

    try:

        Path(temporary).write_text(
            content,
            encoding="utf-8",
        )

        os.replace(
            temporary,
            path,
        )

    finally:

        if os.path.exists(
            temporary
        ):
            os.unlink(
                temporary
            )

    return {
        "path": relative,
        "bytes": len(
            content.encode("utf-8")
        ),
    }


def delete_file(
    root: Path,
    relative: str,
) -> dict[str, Any]:

    path = safe_path(
        root,
        relative,
    )

    if is_sensitive(path):
        raise ValueError(
            "Sensitive files cannot be deleted."
        )

    if not path.is_file():
        raise ValueError(
            "File not found."
        )

    path.unlink()

    return {
        "deleted": relative
    }


def search_files(
    root: Path,
    query: str,
) -> list[dict[str, Any]]:

    matches = []

    for relative in list_tree(
        root
    ):

        path = safe_path(
            root,
            relative,
        )

        if (
            not path.is_file()
            or is_sensitive(path)
        ):
            continue

        if (
            path.stat().st_size
            > MAX_FILE_SIZE
        ):
            continue

        try:

            lines = path.read_text(
                errors="replace"
            ).splitlines()

        except OSError:
            continue

        for number, line in enumerate(
            lines,
            1,
        ):

            if query.lower() in line.lower():

                matches.append(
                    {
                        "path": relative,
                        "line": number,
                        "text": line[:1000],
                    }
                )

                if len(matches) >= 500:
                    return matches

    return matches


# ============================================================
# PROJECT DETECTION
# ============================================================

def detect_project(
    root: Path,
) -> dict[str, Any]:

    names = {
        p.name
        for p in root.iterdir()
    }

    project_type = "unknown"
    framework = None
    package_manager = None

    tests: list[list[str]] = []
    builds: list[list[str]] = []
    typechecks: list[list[str]] = []

    # Python
    if (
        "pyproject.toml" in names
        or "requirements.txt" in names
        or "setup.py" in names
    ):

        project_type = "python"
        package_manager = "pip"

        if (
            (root / "pytest.ini").exists()
            or (root / "tests").exists()
            or "pytest" in (
                root.joinpath(
                    "requirements.txt"
                ).read_text(
                    errors="ignore"
                )
                if (
                    root / "requirements.txt"
                ).exists()
                else ""
            )
        ):
            tests = [
                ["python", "-m", "pytest"]
            ]

        else:

            tests = [
                ["python", "-m", "pytest"]
            ]

    # Node
    elif "package.json" in names:

        project_type = "node"
        package_manager = "npm"

        try:

            package = json.loads(
                (
                    root / "package.json"
                ).read_text(
                    errors="replace"
                )
            )

            scripts = package.get(
                "scripts",
                {}
            )

            dependencies = {
                **package.get(
                    "dependencies",
                    {}
                ),
                **package.get(
                    "devDependencies",
                    {}
                ),
            }

            if "next" in dependencies:
                framework = "Next.js"

            elif "vite" in dependencies:
                framework = "Vite"

            elif "react" in dependencies:
                framework = "React"

            elif "vue" in dependencies:
                framework = "Vue"

            elif "angular" in dependencies:
                framework = "Angular"

            else:
                framework = "Node.js"

            if "test" in scripts:
                tests.append(
                    ["npm", "test"]
                )

            if "build" in scripts:
                builds.append(
                    ["npm", "run", "build"]
                )

            if "typecheck" in scripts:
                typechecks.append(
                    [
                        "npm",
                        "run",
                        "typecheck",
                    ]
                )

            elif "typescript" in dependencies:
                typechecks.append(
                    [
                        "npx",
                        "tsc",
                        "--noEmit",
                    ]
                )

        except Exception:
            pass

    # Go
    elif "go.mod" in names:

        project_type = "go"
        package_manager = "go"

        tests = [
            ["go", "test", "./..."]
        ]

    # Rust
    elif "Cargo.toml" in names:

        project_type = "rust"
        package_manager = "cargo"

        tests = [
            ["cargo", "test"]
        ]

    # Java
    elif "pom.xml" in names:

        project_type = "java"
        package_manager = "maven"

        tests = [
            ["mvn", "test"]
        ]

    elif (
        "build.gradle" in names
        or "build.gradle.kts" in names
    ):

        project_type = "java"
        package_manager = "gradle"

        tests = [
            ["./gradlew", "test"]
        ]

    return {
        "project_type": project_type,
        "framework": framework,
        "package_manager": package_manager,
        "test_commands": tests,
        "build_commands": builds,
        "typecheck_commands": typechecks,
        "files": list_tree(root),
    }


# ============================================================
# GIT
# ============================================================

def git_status(
    root: Path,
) -> dict[str, Any]:

    return run_process(
        [
            "git",
            "status",
            "--short",
        ],
        root,
    )


def git_diff(
    root: Path,
) -> dict[str, Any]:

    status = git_status(
        root
    )

    diff = run_process(
        [
            "git",
            "diff",
        ],
        root,
    )

    stat = run_process(
        [
            "git",
            "diff",
            "--stat",
        ],
        root,
    )

    return {
        "status": status,
        "stat": stat["stdout"],
        "diff": diff["stdout"][
            -MAX_COMMAND_OUTPUT:
        ],
    }


def git_create_branch(
    root: Path,
    branch: str,
) -> dict[str, Any]:

    if not re.fullmatch(
        r"[A-Za-z0-9._/-]+",
        branch,
    ):
        raise ValueError(
            "Invalid branch name."
        )

    return run_process(
        [
            "git",
            "checkout",
            "-b",
            branch,
        ],
        root,
    )


def git_commit(
    root: Path,
    message: str,
) -> dict[str, Any]:

    if len(message.strip()) < 5:
        raise ValueError(
            "Commit message is too short."
        )

    add = run_process(
        [
            "git",
            "add",
            "-A",
        ],
        root,
    )

    if not add["success"]:
        return {
            "add": add,
            "success": False,
        }

    commit = run_process(
        [
            "git",
            "commit",
            "-m",
            message,
        ],
        root,
    )

    sha = None

    if commit["success"]:

        sha_result = run_process(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            root,
        )

        sha = sha_result[
            "stdout"
        ].strip()

    return {
        "add": add,
        "commit": commit,
        "sha": sha,
        "success": commit["success"],
    }


def git_push(
    root: Path,
    branch: str,
) -> dict[str, Any]:

    if not os.getenv(
        "GITHUB_TOKEN"
    ):
        raise ValueError(
            "GITHUB_TOKEN is not configured."
        )

    result = subprocess.run(
        [
            "git",
            "push",
            "origin",
            branch,
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT,
        env=github_env(),
    )

    return {
        "success": result.returncode == 0,
        "branch": branch,
        "stdout": redact(
            result.stdout[-5000:]
        ),
        "stderr": redact(
            result.stderr[-5000:]
        ),
        "exit_code": result.returncode,
    }


# ============================================================
# DIFF SUMMARY
# ============================================================

def diff_summary(
    root: Path,
) -> dict[str, Any]:

    status = run_process(
        [
            "git",
            "status",
            "--short",
        ],
        root,
    )

    modified = []
    added = []
    deleted = []
    renamed = []

    for line in (
        status["stdout"]
        .splitlines()
    ):

        if len(line) < 3:
            continue

        code = line[:2]
        path = line[3:]

        if "?" in code or "A" in code:
            added.append(path)

        elif "D" in code:
            deleted.append(path)

        elif "R" in code:
            renamed.append(path)

        else:
            modified.append(path)

    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "renamed": renamed,
        "total_changed": (
            len(added)
            + len(modified)
            + len(deleted)
            + len(renamed)
        ),
    }


# ============================================================
# SESSIONS
# ============================================================

@dataclass
class Session:

    id: str

    mode: str

    workspace: Path

    repository: dict[str, Any] = field(
        default_factory=dict
    )

    project: dict[str, Any] = field(
        default_factory=dict
    )

    approved_plan: Any = field(
        default_factory=dict
    )

    task: str = ""

    status: str = "created"

    cancelled: bool = False

    logs: list[dict[str, Any]] = field(
        default_factory=list
    )

    iterations: list[dict[str, Any]] = field(
        default_factory=list
    )

    lock: threading.Lock = field(
        default_factory=threading.Lock
    )

    def log(
        self,
        level: str,
        event: str,
        message: str,
        **extra: Any,
    ):

        item = {
            "timestamp": now(),
            "level": level,
            "event": event,
            "message": redact(message),
            **extra,
        }

        with self.lock:
            self.logs.append(item)

        getattr(
            log,
            level
            if level in {
                "debug",
                "info",
                "warning",
                "error",
            }
            else "info",
        )(
            redact(message)
        )


SESSIONS: dict[
    str,
    Session
] = {}


def validate_session_id(
    session_id: str,
):

    if not re.fullmatch(
        r"[A-Za-z0-9_-]{3,80}",
        session_id,
    ):
        raise api_error(
            "INVALID_SESSION_ID",
            "Invalid session ID.",
        )


def new_workspace(
    session_id: str,
) -> Path:

    validate_session_id(
        session_id
    )

    path = (
        BASE_DIR / session_id
    ).resolve()

    try:

        path.relative_to(
            BASE_DIR
        )

    except ValueError:

        raise api_error(
            "WORKSPACE_ERROR",
            "Invalid workspace.",
        )

    if path.exists():
        shutil.rmtree(
            path,
            ignore_errors=True
        )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def get_session(
    session_id: str,
) -> Session:

    session = SESSIONS.get(
        session_id
    )

    if not session:
        raise api_error(
            "SESSION_NOT_FOUND",
            "Work session not found.",
            404,
        )

    return session


# ============================================================
# GEMINI
# ============================================================

class GeminiService:

    def __init__(self):

        self.client = None

        key = os.getenv(
            "GEMINI_API_KEY"
        )

        if (
            genai
            and key
        ):

            self.client = (
                genai.Client(
                    api_key=key
                )
            )

    def text(
        self,
        prompt: str,
        json_mode: bool = False,
    ) -> Any:

        if not self.client:

            raise api_error(
                "AI_NOT_CONFIGURED",
                "Gemini API is not configured.",
                503,
            )

        last_error = None

        for attempt in range(5):

            try:

                config = None

                if (
                    json_mode
                    and types
                ):

                    config = (
                        types.GenerateContentConfig(
                            response_mime_type=(
                                "application/json"
                            )
                        )
                    )

                response = (
                    self.client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt,
                        config=config,
                    )
                )

                text = (
                    response.text
                    or ""
                ).strip()

                if json_mode:

                    # Handle occasional markdown fences.
                    text = re.sub(
                        r"^```(?:json)?\s*",
                        "",
                        text,
                        flags=re.I,
                    )

                    text = re.sub(
                        r"\s*```$",
                        "",
                        text,
                    )

                    return json.loads(
                        text
                    )

                return text

            except Exception as exc:

                last_error = exc

                marker = str(
                    exc
                ).lower()

                retryable = any(
                    token in marker
                    for token in (
                        "429",
                        "503",
                        "unavailable",
                        "resource exhausted",
                        "temporarily",
                        "deadline",
                        "timeout",
                    )
                )

                if (
                    not retryable
                    or attempt == 4
                ):
                    break

                delay = min(
                    2 ** attempt,
                    16,
                )

                time.sleep(
                    delay
                )

        log.error(
            "Gemini error: %s",
            redact(
                str(last_error)
            ),
        )

        raise api_error(
            "AI_REQUEST_FAILED",
            "The AI provider could not complete the request. Please retry.",
            503,
        )


GEMINI = GeminiService()


# ============================================================
# AI PROMPTS
# ============================================================

def context_text(
    value: Any,
) -> str:

    if value is None:
        return ""

    if isinstance(
        value,
        str,
    ):
        return value

    try:

        return json.dumps(
            value,
            ensure_ascii=False,
        )

    except Exception:

        return str(value)


CHAT_SYSTEM = """
You are Open Agent.

You behave like a highly capable ChatGPT-style assistant.

You can:
- discuss ideas
- explain programming
- analyze architecture
- debug concepts
- help with software engineering
- communicate naturally in the user's language
- support multilingual conversation

You are NOT executing repository operations in Chat Mode.

Never falsely claim to have changed a file, committed code,
pushed code, or inspected a repository.

If the user wants repository execution, explain that Work Mode
must be authorized and prepared first.
"""


PLAN_SYSTEM = """
You are Open Agent Plan Mode.

You are a senior software architect.

Analyze the user's goal carefully.

Do not modify files.

Create an implementation plan containing:
- goal
- requirements
- architecture
- affected files
- new files
- dependencies
- implementation steps
- tests
- build/typecheck requirements
- risks
- assumptions
- questions if truly necessary

If repository information is available, reason from it.
Do not invent repository facts.
"""


AGENT_SYSTEM = """
You are Open Agent Work Mode.

You are an autonomous senior software engineering agent.

You have access to a prepared authorized workspace.

Your workflow is:

1. Understand the approved task.
2. Inspect the repository.
3. Read relevant files.
4. Search when necessary.
5. Understand architecture.
6. Make minimal correct changes.
7. Handle multiple files when necessary.
8. Run tests.
9. Run build/typecheck when appropriate.
10. Inspect failures.
11. Diagnose the ROOT CAUSE.
12. Fix the problem.
13. Re-run validation.
14. Repeat error -> diagnosis -> fix -> test.
15. Review git diff.
16. Commit when authorized.
17. Push when authorized.
18. Finish with an accurate report.

Never pretend an operation succeeded.

You MUST use tools/actions when needed.

Do not stop just because the first test fails.
Do not make random fixes.

Allowed actions:

list_files
read_file
search_files
write_file
delete_file
terminal
run_test
run_build
run_typecheck
git_status
git_diff
git_branch
git_commit
git_push
finish

Return ONLY JSON.

JSON format:

{
  "action": "action_name",
  "path": "...",
  "query": "...",
  "content": "...",
  "command": "...",
  "message": "...",
  "reason": "..."
}

Only fields needed for the action are required.

For write_file, provide COMPLETE file content.

Before editing unfamiliar code, inspect it first.

Use terminal for project-specific commands.

Do not expose secrets.

Do not modify .git internals.
"""


# ============================================================
# ACTION VALIDATION
# ============================================================

ALLOWED_ACTIONS = {
    "list_files",
    "read_file",
    "search_files",
    "write_file",
    "delete_file",
    "terminal",
    "run_test",
    "run_build",
    "run_typecheck",
    "git_status",
    "git_diff",
    "git_branch",
    "git_commit",
    "git_push",
    "finish",
}


def validate_action(
    action: dict[str, Any],
) -> str:

    if not isinstance(
        action,
        dict,
    ):
        raise ValueError(
            "AI returned an invalid action."
        )

    name = action.get(
        "action"
    )

    if name not in ALLOWED_ACTIONS:

        raise ValueError(
            f"Unsupported action: {name}"
        )

    return name


# ============================================================
# ACTION EXECUTION
# ============================================================

def execute_action(
    session: Session,
    action: dict[str, Any],
) -> dict[str, Any]:

    root = (
        session.workspace
        / "repo"
    )

    name = validate_action(
        action
    )

    session.log(
        "info",
        "tool",
        f"Executing {name}",
        action=name,
        path=action.get("path"),
    )

    # -----------------------------
    # FILES
    # -----------------------------

    if name == "list_files":

        return {
            "files": list_tree(
                root
            )
        }

    if name == "read_file":

        return {
            "path": action.get(
                "path"
            ),
            "content": read_file(
                root,
                action.get(
                    "path",
                    "",
                ),
            ),
        }

    if name == "search_files":

        return {
            "query": action.get(
                "query",
                "",
            ),
            "matches": search_files(
                root,
                str(
                    action.get(
                        "query",
                        "",
                    )
                ),
            ),
        }

    if name == "write_file":

        return write_file(
            root,
            action.get(
                "path",
                "",
            ),
            action.get(
                "content",
                "",
            ),
        )

    if name == "delete_file":

        relative = action.get(
            "path",
            "",
        )

        if (
            ".git"
            in Path(relative).parts
        ):
            raise ValueError(
                "Cannot modify .git."
            )

        return delete_file(
            root,
            relative,
        )

    # -----------------------------
    # TERMINAL
    # -----------------------------

    if name == "terminal":

        command = str(
            action.get(
                "command",
                "",
            )
        )

        return run_terminal(
            root,
            command,
        )

    # -----------------------------
    # TEST
    # -----------------------------

    if name == "run_test":

        commands = (
            session.project
            .get(
                "test_commands",
                [],
            )
        )

        if not commands:

            return {
                "skipped": True,
                "reason": (
                    "No test command detected."
                ),
            }

        results = []

        for command in commands:

            result = run_process(
                command,
                root,
            )

            results.append(
                result
            )

            if result["success"]:
                break

        return {
            "success": any(
                x["success"]
                for x in results
            ),
            "results": results,
        }

    # -----------------------------
    # BUILD
    # -----------------------------

    if name == "run_build":

        commands = (
            session.project
            .get(
                "build_commands",
                [],
            )
        )

        if not commands:

            return {
                "skipped": True,
                "reason": (
                    "No build command detected."
                ),
            }

        results = []

        for command in commands:

            result = run_process(
                command,
                root,
            )

            results.append(
                result
            )

            if result["success"]:
                break

        return {
            "success": any(
                x["success"]
                for x in results
            ),
            "results": results,
        }

    # -----------------------------
    # TYPECHECK
    # -----------------------------

    if name == "run_typecheck":

        commands = (
            session.project
            .get(
                "typecheck_commands",
                [],
            )
        )

        if not commands:

            return {
                "skipped": True,
                "reason": (
                    "No typecheck command detected."
                ),
            }

        results = []

        for command in commands:

            result = run_process(
                command,
                root,
            )

            results.append(
                result
            )

            if result["success"]:
                break

        return {
            "success": any(
                x["success"]
                for x in results
            ),
            "results": results,
        }

    # -----------------------------
    # GIT
    # -----------------------------

    if name == "git_status":

        return git_status(
            root
        )

    if name == "git_diff":

        return git_diff(
            root
        )

    if name == "git_branch":

        branch = str(
            action.get(
                "branch",
                ""
            )
        )

        return git_create_branch(
            root,
            branch,
        )

    if name == "git_commit":

        return git_commit(
            root,
            str(
                action.get(
                    "message",
                    "",
                )
            ),
        )

    if name == "git_push":

        if not AUTO_PUSH:

            return {
                "success": False,
                "skipped": True,
                "reason": (
                    "AUTO_PUSH is disabled."
                ),
            }

        branch = (
            session.repository
            .get(
                "branch",
            )
        )

        if not branch:

            branch_result = run_process(
                [
                    "git",
                    "branch",
                    "--show-current",
                ],
                root,
            )

            branch = (
                branch_result[
                    "stdout"
                ].strip()
            )

        return git_push(
            root,
            branch,
        )

    # -----------------------------
    # FINISH
    # -----------------------------

    if name == "finish":

        return {
            "finished": True
        }

    raise ValueError(
        "Action was not executed."
    )


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Open Agent",
    version="2.0.0",
    description=(
        "Manus-style autonomous AI software engineering agent."
    ),
)


origins = [
    item.strip()
    for item in os.getenv(
        "FRONTEND_ORIGINS",
        "*",
    ).split(",")
    if item.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class ChatRequest(BaseModel):

    message: str = Field(
        min_length=1,
        max_length=30000,
    )

    conversation_context: Any = None


class PlanRequest(BaseModel):

    task: str = Field(
        min_length=1,
        max_length=30000,
    )

    conversation_context: Any = None

    repo_url: str | None = None


class FinalizeRequest(PlanRequest):

    draft_plan: Any


class RepoRequest(BaseModel):

    repo_url: str


class ReadRequest(RepoRequest):

    file_path: str


class SearchRequest(RepoRequest):

    query: str = Field(
        min_length=1,
        max_length=500,
    )


class WorkPrepareRequest(BaseModel):

    session_id: str

    repo_url: str

    task: str

    approved_plan: Any


class WorkExecuteRequest(BaseModel):

    session_id: str

    task: str

    approved_plan: Any


class TerminalRequest(BaseModel):

    session_id: str

    command: str

    timeout: int | None = None


class EditRequest(BaseModel):

    session_id: str

    file_path: str

    content: str

    commit_message: str = Field(
        min_length=5,
        max_length=200,
    )


class CommitRequest(BaseModel):

    session_id: str

    message: str = Field(
        min_length=5,
        max_length=200,
    )


class PushRequest(BaseModel):

    session_id: str


class BranchRequest(BaseModel):

    session_id: str

    branch: str


class StopRequest(BaseModel):

    session_id: str


# ============================================================
# ROOT / HEALTH
# ============================================================

@app.get("/")
def root():

    return {
        "name": "Open Agent",
        "version": "2.0.0",
        "status": "online",
        "docs": "/docs",
        "capabilities": {
            "chat": True,
            "plan_mode": True,
            "work_mode": True,
            "github": True,
            "repository_read": True,
            "repository_search": True,
            "multi_file_edit": True,
            "terminal": True,
            "testing": True,
            "build": True,
            "typecheck": True,
            "error_fix_loop": True,
            "git_status": True,
            "git_diff": True,
            "git_branch": True,
            "git_commit": True,
            "git_push": True,
            "zip": True,
        },
    }


@app.get("/health")
def health():

    return {
        "status": "ok",
        "model": GEMINI_MODEL,
        "gemini_configured": bool(
            os.getenv(
                "GEMINI_API_KEY"
            )
        ),
        "github_configured": bool(
            os.getenv(
                "GITHUB_TOKEN"
            )
        ),
        "capabilities": {
            "chat": True,
            "plan_mode": True,
            "work_mode": True,
            "github_read": True,
            "github_edit": True,
            "multi_file_edit": True,
            "terminal": True,
            "auto_testing": True,
            "auto_build": True,
            "typecheck": True,
            "error_fix_loop": True,
            "git_status": True,
            "git_diff": True,
            "git_branch": True,
            "commit": True,
            "push": bool(
                os.getenv(
                    "GITHUB_TOKEN"
                )
            ),
            "zip": True,
        },
    }


# ============================================================
# CHAT MODE
# ============================================================

@app.post("/chat")
def chat(
    request: ChatRequest,
):

    prompt = f"""
{CHAT_SYSTEM}

Conversation context:
{context_text(request.conversation_context)}

User:
{request.message}
"""

    reply = GEMINI.text(
        prompt
    )

    return {
        "ok": True,
        "mode": "chat",
        "reply": reply,
    }


# ============================================================
# PLAN MODE
# ============================================================

@app.post("/plan")
def create_plan(
    request: PlanRequest,
):

    prompt = f"""
{PLAN_SYSTEM}

User task:
{request.task}

Repository:
{request.repo_url or "No repository connected"}

Conversation:
{context_text(request.conversation_context)}

Return JSON with:

{{
  "goal": "...",
  "requirements": [],
  "architecture": [],
  "files": [],
  "new_files": [],
  "dependencies": [],
  "steps": [],
  "tests": [],
  "build": [],
  "risks": [],
  "assumptions": [],
  "clarifying_questions": []
}}
"""

    result = GEMINI.text(
        prompt,
        json_mode=True,
    )

    return {
        "ok": True,
        "mode": "plan",
        "plan": result,
    }


# ============================================================
# FINALIZE PLAN
# ============================================================

@app.post("/plan/finalize")
def finalize_plan(
    request: FinalizeRequest,
):

    prompt = f"""
Finalize the following software implementation plan.

Do not modify files.

Do not invent repository facts.

Return ONLY JSON:

{{
  "goal": "...",
  "requirements": [],
  "architecture": [],
  "files": [],
  "changes": [],
  "dependencies": [],
  "tests": [],
  "build": [],
  "risks": [],
  "steps": []
}}

Task:
{request.task}

Draft plan:
{json.dumps(
    request.draft_plan,
    ensure_ascii=False
)}

Conversation:
{context_text(
    request.conversation_context
)}
"""

    result = GEMINI.text(
        prompt,
        json_mode=True,
    )

    return {
        "ok": True,
        "mode": "finalized",
        "approved_plan": result,
        "work_authorization_required": True,
    }


# ============================================================
# REPOSITORY INSPECTION
# ============================================================

def temporary_clone(
    repo_url: str,
):

    session_id = (
        "inspect-"
        + uuid.uuid4().hex[:12]
    )

    workspace = new_workspace(
        session_id
    )

    repo = clone_repo(
        repo_url,
        workspace / "repo",
    )

    return workspace, repo


@app.post("/repository/inspect")
def repository_inspect(
    request: RepoRequest,
):

    workspace, repository = (
        temporary_clone(
            request.repo_url
        )
    )

    try:

        root = (
            workspace / "repo"
        )

        project = detect_project(
            root
        )

        return {
            "ok": True,
            "repository": repository,
            "project": {
                k: v
                for k, v
                in project.items()
                if k
                not in {
                    "files",
                    "test_commands",
                    "build_commands",
                    "typecheck_commands",
                }
            },
            "files": project[
                "files"
            ],
            "commands": {
                "test": project[
                    "test_commands"
                ],
                "build": project[
                    "build_commands"
                ],
                "typecheck": project[
                    "typecheck_commands"
                ],
            },
        }

    finally:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )


@app.post("/repository/read")
def repository_read(
    request: ReadRequest,
):

    workspace, repository = (
        temporary_clone(
            request.repo_url
        )
    )

    try:

        content = read_file(
            workspace / "repo",
            request.file_path,
        )

        return {
            "ok": True,
            "repository": repository,
            "path": request.file_path,
            "content": content,
        }

    finally:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )


@app.post("/repository/search")
def repository_search(
    request: SearchRequest,
):

    workspace, repository = (
        temporary_clone(
            request.repo_url
        )
    )

    try:

        matches = search_files(
            workspace / "repo",
            request.query,
        )

        return {
            "ok": True,
            "repository": repository,
            "query": request.query,
            "matches": matches,
        }

    finally:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )


# ============================================================
# WORK PREPARE
# ============================================================

@app.post("/work/prepare")
def work_prepare(
    request: WorkPrepareRequest,
):

    if not request.approved_plan:
        raise api_error(
            "PLAN_REQUIRED",
            "A finalized approved plan is required.",
        )

    workspace = new_workspace(
        request.session_id
    )

    session = Session(
        id=request.session_id,
        mode="work",
        workspace=workspace,
        task=request.task,
        approved_plan=request.approved_plan,
    )

    SESSIONS[
        request.session_id
    ] = session

    try:

        repository = clone_repo(
            request.repo_url,
            workspace / "repo",
        )

        session.repository = (
            repository
        )

        root = (
            workspace / "repo"
        )

        branch = (
            f"open-agent/"
            f"{request.session_id}"
        )

        branch_result = (
            git_create_branch(
                root,
                branch,
            )
        )

        if not branch_result[
            "success"
        ]:

            raise api_error(
                "BRANCH_FAILED",
                branch_result[
                    "stderr"
                ],
                400,
            )

        session.repository[
            "branch"
        ] = branch

        session.project = (
            detect_project(root)
        )

        session.status = (
            "prepared"
        )

        session.log(
            "info",
            "workspace",
            "Work Mode prepared.",
            repository=repository,
            branch=branch,
        )

        return {
            "ok": True,
            "session_id": session.id,
            "status": session.status,
            "repository": session.repository,
            "project": session.project,
        }

    except Exception:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )

        SESSIONS.pop(
            request.session_id,
            None,
        )

        raise


# ============================================================
# WORK TERMINAL
# ============================================================

@app.post("/work/terminal")
def work_terminal(
    request: TerminalRequest,
):

    session = get_session(
        request.session_id
    )

    if session.mode != "work":
        raise api_error(
            "WORK_MODE_REQUIRED",
            "Terminal requires Work Mode.",
        )

    if session.status not in {
        "prepared",
        "running",
    }:

        raise api_error(
            "INVALID_SESSION_STATE",
            "Work session is not executable.",
        )

    root = (
        session.workspace / "repo"
    )

    try:

        result = run_terminal(
            root,
            request.command,
            request.timeout,
        )

        session.log(
            "info",
            "terminal",
            f"Terminal executed: {request.command}",
            result=result,
        )

        return {
            "ok": True,
            "result": result,
        }

    except subprocess.TimeoutExpired:

        return {
            "ok": False,
            "result": {
                "command": request.command,
                "success": False,
                "exit_code": -1,
                "stderr": "Command timed out.",
            },
        }

    except Exception as exc:

        raise api_error(
            "TERMINAL_ERROR",
            redact(str(exc)),
            400,
        )


# ============================================================
# WORK EDIT
# ============================================================

@app.post("/repository/edit")
def repository_edit(
    request: EditRequest,
):

    session = get_session(
        request.session_id
    )

    if session.mode != "work":
        raise api_error(
            "WORK_MODE_REQUIRED",
            "Work Mode is required.",
        )

    if session.status not in {
        "prepared",
        "running",
    }:

        raise api_error(
            "INVALID_SESSION_STATE",
            "Session is not editable.",
        )

    root = (
        session.workspace / "repo"
    )

    result = write_file(
        root,
        request.file_path,
        request.content,
    )

    diff = diff_summary(
        root
    )

    return {
        "ok": True,
        "edit": result,
        "diff": diff,
    }


# ============================================================
# WORK COMMIT
# ============================================================

@app.post("/work/commit")
def work_commit(
    request: CommitRequest,
):

    session = get_session(
        request.session_id
    )

    if session.mode != "work":
        raise api_error(
            "WORK_MODE_REQUIRED",
            "Work Mode is required.",
        )

    root = (
        session.workspace / "repo"
    )

    diff = diff_summary(
        root
    )

    if diff["total_changed"] == 0:

        return {
            "ok": True,
            "committed": False,
            "reason": "No changes to commit.",
        }

    result = git_commit(
        root,
        request.message,
    )

    return {
        "ok": result["success"],
        "commit": result,
        "diff": diff_summary(
            root
        ),
    }


# ============================================================
# WORK PUSH
# ============================================================

@app.post("/work/push")
def work_push(
    request: PushRequest,
):

    session = get_session(
        request.session_id
    )

    if session.mode != "work":
        raise api_error(
            "WORK_MODE_REQUIRED",
            "Work Mode is required.",
        )

    if not os.getenv(
        "GITHUB_TOKEN"
    ):

        raise api_error(
            "GITHUB_TOKEN_MISSING",
            "GITHUB_TOKEN is not configured.",
            503,
        )

    root = (
        session.workspace / "repo"
    )

    branch = session.repository.get(
        "branch"
    )

    if not branch:

        result = run_process(
            [
                "git",
                "branch",
                "--show-current",
            ],
            root,
        )

        branch = (
            result["stdout"]
            .strip()
        )

    result = git_push(
        root,
        branch,
    )

    return {
        "ok": result["success"],
        "push": result,
    }


# ============================================================
# AUTONOMOUS WORK LOOP
# ============================================================

@app.post("/work/execute")
def work_execute(
    request: WorkExecuteRequest,
):

    session = get_session(
        request.session_id
    )

    if session.mode != "work":
        raise api_error(
            "WORK_MODE_REQUIRED",
            "Work Mode is required.",
        )

    if (
        request.task
        != session.task
    ):

        raise api_error(
            "TASK_MISMATCH",
            "Task does not match authorization.",
        )

    if (
        context_text(
            request.approved_plan
        )
        != context_text(
            session.approved_plan
        )
    ):

        raise api_error(
            "PLAN_MISMATCH",
            "Approved plan does not match authorization.",
        )

    session.status = "running"

    root = (
        session.workspace / "repo"
    )

    last_result = None
    consecutive_errors = 0

    try:

        for iteration in range(
            1,
            MAX_AGENT_ITERATIONS + 1,
        ):

            if session.cancelled:

                session.status = (
                    "stopped"
                )

                return {
                    "ok": False,
                    "status": "stopped",
                    "reason": "Work cancelled.",
                }

            current_diff = (
                diff_summary(
                    root
                )
            )

            recent_logs = (
                session.iterations[
                    -5:
                ]
            )

            prompt = f"""
{AGENT_SYSTEM}

TASK:
{session.task}

APPROVED PLAN:
{json.dumps(
    session.approved_plan,
    ensure_ascii=False
)}

REPOSITORY:
{json.dumps(
    session.repository,
    ensure_ascii=False
)}

PROJECT:
{json.dumps(
    session.project,
    ensure_ascii=False
)}

CURRENT DIFF:
{json.dumps(
    current_diff,
    ensure_ascii=False
)}

LAST RESULT:
{json.dumps(
    last_result,
    ensure_ascii=False
)}

RECENT ITERATIONS:
{json.dumps(
    recent_logs,
    ensure_ascii=False
)}

Iteration:
{iteration}

Choose the NEXT best action.

Important:
- Inspect before editing.
- Use multi-file edits when required.
- Use terminal when project commands are necessary.
- After implementation, test it.
- If test/build/typecheck fails, diagnose and fix it.
- Do not finish while known fixable errors remain.
- Do not invent files or command output.
"""

            action = GEMINI.text(
                prompt,
                json_mode=True,
            )

            try:

                result = execute_action(
                    session,
                    action,
                )

                consecutive_errors = 0

            except Exception as exc:

                result = {
                    "success": False,
                    "error": redact(
                        str(exc)
                    ),
                }

                consecutive_errors += 1

                session.log(
                    "error",
                    "action_error",
                    str(exc),
                )

                # Let the AI diagnose the
                # actual error on the next loop.

            record = {
                "iteration": iteration,
                "action": action,
                "result": result,
                "diff": diff_summary(
                    root
                ),
                "timestamp": now(),
            }

            session.iterations.append(
                record
            )

            last_result = result

            if (
                action.get(
                    "action"
                )
                == "finish"
            ):

                session.status = (
                    "completed"
                )

                break

            # Prevent infinite broken loops.
            if (
                consecutive_errors
                >= 5
            ):

                session.status = (
                    "failed"
                )

                break

        else:

            session.status = (
                "partial"
            )

        final_diff = diff_summary(
            root
        )

        return {
            "ok": session.status
            in {
                "completed",
                "partial",
            },
            "status": session.status,
            "session_id": session.id,
            "repository": session.repository,
            "files_changed": final_diff,
            "iterations": session.iterations,
            "summary": (
                "Work completed."
                if session.status
                == "completed"
                else
                "Work stopped after the configured iteration limit."
            ),
        }

    except Exception as exc:

        session.status = (
            "failed"
        )

        session.log(
            "error",
            "work",
            "Autonomous execution failed.",
            error=str(exc),
        )

        return {
            "ok": False,
            "status": "failed",
            "error": redact(
                str(exc)
            ),
            "files_changed": diff_summary(
                root
            ),
            "iterations": session.iterations,
        }


# ============================================================
# STOP
# ============================================================

@app.post("/work/stop")
def work_stop(
    request: StopRequest,
):

    session = get_session(
        request.session_id
    )

    session.cancelled = True
    session.status = "stopped"

    session.log(
        "warning",
        "work",
        "Cancellation requested.",
    )

    return {
        "ok": True,
        "status": "stopped",
    }


# ============================================================
# STATUS
# ============================================================

@app.get(
    "/work/status/{session_id}"
)
def work_status(
    session_id: str,
):

    session = get_session(
        session_id
    )

    root = (
        session.workspace / "repo"
    )

    return {
        "ok": True,
        "session_id": session.id,
        "mode": session.mode,
        "status": session.status,
        "cancelled": session.cancelled,
        "repository": session.repository,
        "project": {
            "project_type":
                session.project.get(
                    "project_type"
                ),
            "framework":
                session.project.get(
                    "framework"
                ),
            "package_manager":
                session.project.get(
                    "package_manager"
                ),
        },
        "files_changed": (
            diff_summary(root)
            if root.exists()
            else {}
        ),
        "iterations": len(
            session.iterations
        ),
    }


@app.get(
    "/work/logs/{session_id}"
)
def work_logs(
    session_id: str,
):

    session = get_session(
        session_id
    )

    return {
        "ok": True,
        "session_id": session.id,
        "logs": session.logs,
        "iterations": session.iterations,
    }


# ============================================================
# ZIP UPLOAD
# ============================================================

@app.post("/project/upload")
async def project_upload(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):

    if (
        not file.filename
        or not file.filename.lower()
        .endswith(".zip")
    ):

        raise api_error(
            "INVALID_FILE",
            "Only ZIP files are supported.",
        )

    workspace = new_workspace(
        session_id
    )

    session = Session(
        id=session_id,
        mode="work",
        workspace=workspace,
        task="Uploaded project",
        approved_plan={},
    )

    SESSIONS[
        session_id
    ] = session

    archive = await file.read()

    if len(archive) > (
        MAX_FILE_SIZE * 100
    ):

        raise api_error(
            "ARCHIVE_TOO_LARGE",
            "ZIP archive is too large.",
        )

    root = (
        workspace / "repo"
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        with zipfile.ZipFile(
            io.BytesIO(archive)
        ) as archive_file:

            for entry in (
                archive_file.infolist()
            ):

                target = safe_path(
                    root,
                    entry.filename,
                    allow_root=True,
                )

                if entry.is_dir():

                    target.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    continue

                if (
                    entry.file_size
                    > MAX_FILE_SIZE
                ):

                    raise api_error(
                        "FILE_TOO_LARGE",
                        "ZIP entry is too large.",
                    )

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                target.write_bytes(
                    archive_file.read(
                        entry
                    )
                )

    except zipfile.BadZipFile:

        raise api_error(
            "INVALID_ZIP",
            "Invalid ZIP archive.",
        )

    session.project = (
        detect_project(root)
    )

    session.status = (
        "prepared"
    )

    return {
        "ok": True,
        "session_id": session_id,
        "project": session.project,
    }


# ============================================================
# ZIP DOWNLOAD
# ============================================================

@app.get(
    "/project/download/{session_id}"
)
def project_download(
    session_id: str,
):

    session = get_session(
        session_id
    )

    root = (
        session.workspace / "repo"
    )

    if not root.exists():

        raise api_error(
            "PROJECT_NOT_FOUND",
            "Project workspace not found.",
            404,
        )

    archive_path = (
        session.workspace
        / "open-agent-result.zip"
    )

    with zipfile.ZipFile(
        archive_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:

        for relative in list_tree(
            root
        ):

            path = safe_path(
                root,
                relative,
            )

            if (
                path.is_file()
                and not is_sensitive(
                    path
                )
            ):

                archive.write(
                    path,
                    relative,
                )

    return FileResponse(
        archive_path,
        filename=(
            f"open-agent-"
            f"{session_id}.zip"
        ),
        media_type=(
            "application/zip"
        ),
    )


# ============================================================
# STARTUP CLEANUP
# ============================================================

@app.on_event(
    "startup"
)
async def startup_cleanup():

    cutoff = (
        time.time()
        - WORKSPACE_TIMEOUT
    )

    try:

        for path in BASE_DIR.iterdir():

            try:

                if (
                    path.is_dir()
                    and path.stat()
                    .st_mtime
                    < cutoff
                ):

                    shutil.rmtree(
                        path,
                        ignore_errors=True,
                    )

            except OSError:
                continue

    except OSError:
        pass


# ============================================================
# LOCAL SERVER
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "8000",
            )
        ),
        reload=False,
    )
