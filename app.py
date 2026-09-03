"""
OPEN AGENT
Advanced Autonomous AI Software Engineering Backend

Architecture:
    Frontend
       |
       v
    FastAPI
       |
       +---- AI Provider Router
       |
       +---- GitHub
       |
       +---- Local Workspace
       |
       +---- Git / Test / Build / Typecheck
       |
       v
    Autonomous Work Agent

Modes:
    CHAT
    PLAN
    WORK

Important:
    - Work Mode requires explicit authorization.
    - AI capabilities are based on actual backend capabilities.
    - Secrets are never returned to frontend.
    - The agent must never claim an operation succeeded without confirmation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
import zipfile

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ai.base import ProviderFailure
from ai.router import ai_router, chat_plan_router


# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "Open Agent"
APP_VERSION = "2.0.0"
LOGGER = logging.getLogger(APP_NAME)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

WORKSPACE_ROOT = Path(
    os.getenv("WORKSPACE_ROOT", "/tmp/open-agent")
).resolve()

UPLOAD_ROOT = WORKSPACE_ROOT / "uploads"
EXPORT_ROOT = WORKSPACE_ROOT / "exports"

MAX_AGENT_ITERATIONS = int(
    os.getenv("MAX_AGENT_ITERATIONS", "20")
)

MAX_TEST_ITERATIONS = int(
    os.getenv("MAX_TEST_ITERATIONS", "5")
)

COMMAND_TIMEOUT = int(
    os.getenv("COMMAND_TIMEOUT", "180")
)

WORKSPACE_TIMEOUT = int(
    os.getenv("WORKSPACE_TIMEOUT", "600")
)

MAX_FILE_SIZE = int(
    os.getenv("MAX_FILE_SIZE", str(2 * 1024 * 1024))
)

MAX_UPLOAD_SIZE = int(
    os.getenv("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024))
)

MAX_ZIP_FILES = int(os.getenv("MAX_ZIP_FILES", "10000"))
MAX_ZIP_UNCOMPRESSED_SIZE = int(
    os.getenv("MAX_ZIP_UNCOMPRESSED_SIZE", str(500 * 1024 * 1024))
)
SESSION_TTL = int(os.getenv("SESSION_TTL", str(60 * 60)))

MAX_SEARCH_RESULTS = int(
    os.getenv("MAX_SEARCH_RESULTS", "100")
)

AUTO_PUSH = os.getenv(
    "AUTO_PUSH",
    "false",
).lower() == "true"

FRONTEND_ORIGINS = os.getenv(
    "FRONTEND_ORIGINS",
    "*",
)

if FRONTEND_ORIGINS.strip() == "*":
    ALLOWED_ORIGINS = ["*"]
else:
    ALLOWED_ORIGINS = [
        x.strip()
        for x in FRONTEND_ORIGINS.split(",")
        if x.strip()
    ]


WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
EXPORT_ROOT.mkdir(parents=True, exist_ok=True)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Open Agent API",
    description=(
        "Advanced autonomous AI software engineering agent "
        "with Chat, Plan and authorized Work modes."
    ),
    version=APP_VERSION,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# CAPABILITIES
# ============================================================

CAPABILITIES: Dict[str, bool] = {
    "chat": True,
    "multilingual": True,

    "plan_mode": True,
    "plan_finalize": True,

    "work_mode": True,
    "work_authorization": True,

    "github_read": bool(GITHUB_TOKEN),
    "github_edit": bool(GITHUB_TOKEN),

    "repository_inspect": True,
    "repository_read": True,
    "repository_search": True,

    "file_create": True,
    "file_edit": True,
    "file_delete": True,
    "multi_file_edit": True,

    "git_status": True,
    "git_diff": True,

    "terminal": True,
    "command_execution": True,

    "auto_testing": True,
    "auto_build": True,
    "auto_typecheck": True,

    "error_fix_loop": True,

    "zip_upload": True,
    "zip_download": True,

    "commit": True,
    "push": bool(GITHUB_TOKEN),

    "background_work": True,
    "work_logs": True,
    "work_stop": True,
}


# ============================================================
# AGENT SYSTEM SPECIFICATION
# ============================================================

AGENT_SYSTEM_PROMPT = r"""
You are OPEN AGENT, an advanced autonomous AI software engineering agent.

You are not merely a chatbot.

You operate through a backend that exposes real software-engineering
capabilities.

============================================================
CORE PRINCIPLE
============================================================

Your capabilities are determined by the backend tools and current
authorized work session.

Never invent a capability.

Never claim that something happened unless the backend actually
executed it and returned confirmation.

Examples:

WRONG:
"I pushed the code to GitHub."

if backend did not confirm push.

CORRECT:
"I could not push the changes because the backend reported..."

============================================================
MODES
============================================================

1. CHAT MODE
------------------------------------------------------------

Chat Mode is normal conversational AI.

You can:
- explain
- teach
- answer questions
- discuss programming
- discuss architecture
- communicate in any language supported by the model

Chat Mode must not modify repository files.

Chat Mode must not commit or push.

------------------------------------------------------------

2. PLAN MODE
------------------------------------------------------------

Plan Mode is for requirements and planning.

You should:
- understand the user's goal
- ask useful questions when necessary
- identify affected areas
- propose implementation strategy
- propose file changes
- propose testing strategy
- revise the plan when the user requests changes

Plan Mode must NOT modify files.

Plan Mode must NOT commit.

Plan Mode must NOT push.

The user must explicitly finalize the plan.

------------------------------------------------------------

3. WORK MODE
------------------------------------------------------------

Work Mode is autonomous software engineering.

Work Mode starts only after explicit user authorization.

Once authorized, you may:

- inspect repository
- inspect project structure
- read files
- search files
- create files
- edit files
- delete files
- modify multiple files
- run tests
- run builds
- run typechecks
- inspect git status
- inspect git diff
- diagnose errors
- fix errors
- retest
- review changes
- commit
- push

Only perform capabilities actually exposed by backend.

============================================================
AUTONOMOUS WORKFLOW
============================================================

Follow this sequence whenever practical:

1. Understand task
2. Inspect repository
3. Detect project type
4. Read relevant files
5. Search relevant code
6. Determine implementation
7. Implement changes
8. Review changed files
9. Run tests
10. If failure:
       diagnose
       identify root cause
       fix
       test again
11. Run build/typecheck when relevant
12. Review final diff
13. Commit only when authorized/required
14. Push only when authorized/required
15. Report actual result

Do not stop merely because the first test failed.

Use an error -> fix -> retest loop.

============================================================
MULTI-FILE ENGINEERING
============================================================

Real software tasks often require multiple files.

Do not artificially limit yourself to one file.

Examples:

Frontend bug:
- component
- API client
- state management
- styles
- tests

Backend bug:
- route
- service
- schema
- database
- tests

Configuration:
- package file
- source file
- environment handling
- documentation

============================================================
TESTING
============================================================

Detect project type.

Python:
- pytest
- python -m pytest

Node:
- npm test
- npm run test

TypeScript:
- npm run typecheck
- npx tsc --noEmit

Build:
- npm run build

Go:
- go test ./...

Rust:
- cargo test

Java:
- Maven/Gradle tests

Only run commands that are appropriate to the detected project.

============================================================
ERROR HANDLING
============================================================

When a test/build/typecheck fails:

1. Read the error.
2. Identify the root cause.
3. Locate relevant source.
4. Apply a targeted fix.
5. Run the failed operation again.
6. Repeat until:
   - fixed,
   - retry limit reached,
   - or the failure is genuinely external.

Do not hide errors.

Do not claim success when tests failed.

============================================================
GITHUB
============================================================

GitHub access is provided by backend.

Never request or expose GITHUB_TOKEN.

Never put GitHub credentials in:
- source code
- URLs
- frontend
- logs
- responses

Use the backend's GitHub capability.

============================================================
FILE OPERATIONS
============================================================

Always respect the active workspace.

Do not modify files outside the active workspace.

Before destructive changes:
- inspect target
- make sure it is relevant
- preserve unrelated user work

Never blindly delete an entire project.

============================================================
TERMINAL
============================================================

Terminal output must represent real commands executed by backend.

Do not fabricate terminal output.

============================================================
COMMUNICATION
============================================================

Talk naturally like a highly capable AI engineering assistant.

Do not repeatedly say:
"I cannot access GitHub"

when the backend provides GitHub access.

Instead determine actual capability and session state.

If an operation is unavailable, explain exactly why.

============================================================
FINAL REPORT
============================================================

At completion report:

- what changed
- files changed
- tests run
- test results
- build/typecheck results
- errors encountered
- fixes applied
- git status
- commit result if performed
- push result if performed

Never invent any result.
"""


# ============================================================
# MODELS
# ============================================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class PlanRequest(BaseModel):
    message: str = Field(min_length=1)
    context: Optional[str] = None


class FinalizePlanRequest(BaseModel):
    session_id: str
    plan: Optional[str] = None


class RepoRequest(BaseModel):
    repository_url: str
    branch: Optional[str] = None


class SessionRequest(BaseModel):
    session_id: str


class ReadFileRequest(BaseModel):
    session_id: str
    path: str


class SearchRequest(BaseModel):
    session_id: str
    query: str


class EditFileRequest(BaseModel):
    session_id: str
    path: str
    content: str


class WorkPrepareRequest(BaseModel):
    session_id: Optional[str] = None
    repository_url: Optional[str] = None
    branch: Optional[str] = None
    authorization: bool = False


class WorkExecuteRequest(BaseModel):
    session_id: str
    task: Optional[str] = None


class CommitRequest(BaseModel):
    session_id: str
    message: Optional[str] = None


class PushRequest(BaseModel):
    session_id: str
    branch: Optional[str] = None


# ============================================================
# SESSION
# ============================================================

@dataclass
class AgentSession:
    id: str

    mode: str = "chat"

    workspace: Optional[Path] = None

    repository: Optional[Dict[str, Any]] = None
    project: Optional[Dict[str, Any]] = None

    plan: Optional[str] = None
    plan_finalized: bool = False

    authorized: bool = False

    task: Optional[str] = None

    status: str = "created"

    cancelled: bool = False

    iterations: int = 0
    test_iterations: int = 0

    logs: List[Dict[str, Any]] = field(
        default_factory=list
    )

    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    last_accessed_at: float = field(default_factory=time.time)

    lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
    )


SESSIONS: Dict[str, AgentSession] = {}

SESSIONS_LOCK = threading.RLock()


def create_session(
    mode: str = "chat",
) -> AgentSession:

    session = AgentSession(
        id=str(uuid.uuid4()),
        mode=mode,
    )

    with SESSIONS_LOCK:
        SESSIONS[session.id] = session

    return session


def get_session(
    session_id: str,
) -> AgentSession:

    with SESSIONS_LOCK:
        session = SESSIONS.get(session_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    now = time.time()
    with session.lock:
        last_accessed = session.last_accessed_at
        if session.finished_at and now - last_accessed > SESSION_TTL:
            raise HTTPException(status_code=404, detail="Session expired")
        session.last_accessed_at = now

    return session


def cleanup_expired_sessions() -> None:
    """Remove completed sessions and their workspaces after the retention window."""
    cutoff = time.time() - SESSION_TTL
    expired: List[AgentSession] = []
    with SESSIONS_LOCK:
        for session_id, session in list(SESSIONS.items()):
            with session.lock:
                if session.finished_at and session.last_accessed_at < cutoff:
                    expired.append(session)
                    del SESSIONS[session_id]

    for session in expired:
        if session.workspace:
            shutil.rmtree(session.workspace.parent, ignore_errors=True)
        (UPLOAD_ROOT / f"{session.id}.zip").unlink(missing_ok=True)
        (EXPORT_ROOT / f"{session.id}.zip").unlink(missing_ok=True)


# ============================================================
# LOGGING
# ============================================================

def log_event(
    session: AgentSession,
    event: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:

    entry = {
        "timestamp": time.time(),
        "event": event,
        "message": message,
    }

    if data:
        entry["data"] = data

    with session.lock:
        session.logs.append(entry)

        # Keep memory bounded.
        if len(session.logs) > 1000:
            del session.logs[:-1000]


# ============================================================
# PROVIDER-INDEPENDENT AI SERVICE
# ============================================================

class AIService:

    def __init__(self, router=chat_plan_router) -> None:
        self.router = router

    def available(self) -> bool:
        return self.router.available()

    async def text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        try:
            return await self.router.generate(
                prompt,
                system,
                temperature,
            )
        except ProviderFailure as exc:
            LOGGER.warning(
                "AI provider request failed: %s",
                str(exc)[:800],
            )
            raise HTTPException(
                status_code=503,
                detail="AI provider is currently unavailable. Please try again later.",
            ) from exc


ai_service = AIService(chat_plan_router)
work_ai_service = AIService(ai_router)


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(
    text: str,
) -> Optional[Any]:

    text = text.strip()

    # Direct JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Markdown code block
    match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if match:
        try:
            return json.loads(
                match.group(1)
            )
        except Exception:
            pass

    # First object
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        try:
            return json.loads(
                text[start:end + 1]
            )
        except Exception:
            pass

    return None


# ============================================================
# SAFE PATH HANDLING
# ============================================================

def safe_path(
    session: AgentSession,
    relative_path: str,
) -> Path:

    if not session.workspace:
        raise HTTPException(
            status_code=400,
            detail="Session has no workspace.",
        )

    relative_path = (
        relative_path
        .replace("\\", "/")
        .strip()
    )

    if not relative_path:
        raise HTTPException(
            status_code=400,
            detail="File path is required.",
        )

    candidate = (
        session.workspace
        / relative_path
    ).resolve()

    try:
        candidate.relative_to(
            session.workspace.resolve()
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Path escapes workspace.",
        )

    return candidate


# ============================================================
# SECRET-SAFE ENVIRONMENT
# ============================================================

def safe_environment() -> Dict[str, str]:

    env = dict(os.environ)

    secret_names = {
        "GITHUB_TOKEN",
        "OPENROUTER_API_KEY_1",
        "OPENROUTER_API_KEY_2",
        "OPENROUTER_API_KEY_3",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "GH_TOKEN",
    }

    for key in secret_names:
        env.pop(key, None)

    return env


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_process(
    command: List[str],
    cwd: Path,
    timeout: int = COMMAND_TIMEOUT,
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:

    if not cwd.exists():
        raise RuntimeError(
            f"Working directory does not exist: {cwd}"
        )

    start = time.time()

    try:

        environment = safe_environment()
        if extra_env:
            environment.update(extra_env)

        process = subprocess.run(
            command,
            cwd=str(cwd),
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )

        return {
            "command": command,
            "returncode": process.returncode,
            "stdout": process.stdout[-30000:],
            "stderr": process.stderr[-30000:],
            "duration": round(
                time.time() - start,
                2,
            ),
            "ok": process.returncode == 0,
        }

    except subprocess.TimeoutExpired as exc:

        return {
            "command": command,
            "returncode": -1,
            "stdout": (
                exc.stdout[-30000:]
                if isinstance(exc.stdout, str)
                else ""
            ),
            "stderr": (
                exc.stderr[-30000:]
                if isinstance(exc.stderr, str)
                else ""
            ),
            "duration": round(
                time.time() - start,
                2,
            ),
            "ok": False,
            "timeout": True,
        }


# ============================================================
# GITHUB
# ============================================================

GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/"
    r"([^/\s]+)/([^/\s]+?)"
    r"(?:\.git)?/?$",
    re.IGNORECASE,
)


def parse_github(
    url: str,
) -> Tuple[str, str]:

    url = url.strip()

    match = GITHUB_URL_RE.match(url)

    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub repository URL.",
        )

    owner = match.group(1)
    repo = match.group(2)

    if repo.endswith(".git"):
        repo = repo[:-4]

    return owner, repo


def github_auth_config() -> str:

    if not GITHUB_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN is not configured.",
        )

    return (
        "credential.helper=!f() { "
        "echo username=x-access-token; "
        "echo password=$GITHUB_TOKEN; "
        "}; f"
    )


def github_auth_environment() -> Dict[str, str]:
    if not GITHUB_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN is not configured.",
        )
    return {
        "GITHUB_TOKEN": GITHUB_TOKEN,
        "GIT_TERMINAL_PROMPT": "0",
    }


def clone_repo(
    repository_url: str,
    branch: Optional[str],
    destination: Path,
) -> Dict[str, Any]:

    if not GITHUB_TOKEN:
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub access is not configured. "
                "Set GITHUB_TOKEN on the backend."
            ),
        )

    parse_github(repository_url)

    if destination.exists():
        shutil.rmtree(destination)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "git",
        "-c",
        github_auth_config(),
        "clone",
    ]

    if branch:
        command += [
            "--branch",
            branch,
        ]

    command += [
        repository_url,
        str(destination),
    ]

    result = run_process(
        command,
        WORKSPACE_ROOT,
        timeout=WORKSPACE_TIMEOUT,
        extra_env=github_auth_environment(),
    )

    if not result["ok"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "GitHub clone failed.",
                "stderr": result["stderr"],
            },
        )

    # Ensure git doesn't accidentally persist auth config.
    try:
        run_process(
            [
                "git",
                "config",
                "--local",
                "--unset-all",
                "http.extraheader",
            ],
            destination,
            timeout=30,
        )
    except Exception:
        pass

    return result


# ============================================================
# GIT
# ============================================================

def git_status(
    workspace: Path,
) -> Dict[str, Any]:

    result = run_process(
        [
            "git",
            "status",
            "--short",
            "--branch",
        ],
        workspace,
    )

    return result


def git_diff(
    workspace: Path,
) -> Dict[str, Any]:

    result = run_process(
        [
            "git",
            "diff",
            "--",
        ],
        workspace,
    )

    return result


def git_commit(
    workspace: Path,
    message: str,
) -> Dict[str, Any]:

    run_process(
        [
            "git",
            "config",
            "user.name",
            "Open Agent",
        ],
        workspace,
    )

    run_process(
        [
            "git",
            "config",
            "user.email",
            "open-agent@localhost",
        ],
        workspace,
    )

    add_result = run_process(
        [
            "git",
            "add",
            "-A",
        ],
        workspace,
    )

    if not add_result["ok"]:
        return add_result

    return run_process(
        [
            "git",
            "commit",
            "-m",
            message,
        ],
        workspace,
    )


def git_push(
    workspace: Path,
    branch: Optional[str] = None,
) -> Dict[str, Any]:

    if not GITHUB_TOKEN:
        return {
            "ok": False,
            "returncode": -1,
            "stderr": (
                "GITHUB_TOKEN is not configured."
            ),
        }

    current_branch = run_process(
        [
            "git",
            "branch",
            "--show-current",
        ],
        workspace,
    )

    current = (
        current_branch["stdout"].strip()
        if current_branch["ok"]
        else ""
    )

    target = branch or current

    if not target:
        target = "main"

    return run_process(
        [
            "git",
            "-c",
            github_auth_config(),
            "push",
            "origin",
            target,
        ],
        workspace,
        timeout=WORKSPACE_TIMEOUT,
        extra_env=github_auth_environment(),
    )


# ============================================================
# FILE TREE
# ============================================================

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".cache",
    "coverage",
}


def list_tree(
    workspace: Path,
    max_items: int = 2000,
) -> List[Dict[str, Any]]:

    items: List[Dict[str, Any]] = []

    for path in workspace.rglob("*"):

        if any(
            part in IGNORED_DIRECTORIES
            for part in path.parts
        ):
            continue

        try:
            relative = path.relative_to(
                workspace
            )
        except ValueError:
            continue

        if len(items) >= max_items:
            break

        items.append(
            {
                "path": str(relative).replace(
                    "\\",
                    "/",
                ),
                "type": (
                    "directory"
                    if path.is_dir()
                    else "file"
                ),
            }
        )

    return sorted(
        items,
        key=lambda x: x["path"],
    )


# ============================================================
# PROJECT DETECTION
# ============================================================

def detect_project(
    workspace: Path,
) -> Dict[str, Any]:

    files = {
        p.name.lower()
        for p in workspace.iterdir()
    }

    project_type = "unknown"

    if (
        "package.json" in files
        or "package-lock.json" in files
    ):
        project_type = "node"

    elif (
        "pyproject.toml" in files
        or "requirements.txt" in files
        or "setup.py" in files
    ):
        project_type = "python"

    elif (
        "go.mod" in files
    ):
        project_type = "go"

    elif (
        "cargo.toml" in files
    ):
        project_type = "rust"

    elif (
        "pom.xml" in files
    ):
        project_type = "java-maven"

    elif (
        "build.gradle" in files
        or "build.gradle.kts" in files
    ):
        project_type = "java-gradle"

    return {
        "type": project_type,
        "root": str(workspace),
        "files": sorted(files),
    }


# ============================================================
# FILE READING
# ============================================================

def read_file(
    path: Path,
) -> str:

    if not path.exists():
        raise FileNotFoundError(
            str(path)
        )

    if not path.is_file():
        raise IsADirectoryError(
            str(path)
        )

    size = path.stat().st_size

    if size > MAX_FILE_SIZE:
        raise ValueError(
            f"File exceeds MAX_FILE_SIZE: {size}"
        )

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


# ============================================================
# SEARCH
# ============================================================

def search_files(
    workspace: Path,
    query: str,
) -> List[Dict[str, Any]]:

    results: List[Dict[str, Any]] = []

    query_lower = query.lower()

    for path in workspace.rglob("*"):

        if len(results) >= MAX_SEARCH_RESULTS:
            break

        if not path.is_file():
            continue

        if any(
            part in IGNORED_DIRECTORIES
            for part in path.parts
        ):
            continue

        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue

            content = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        except Exception:
            continue

        lines = content.splitlines()

        for index, line in enumerate(lines, 1):

            if query_lower in line.lower():

                results.append(
                    {
                        "path": str(
                            path.relative_to(
                                workspace
                            )
                        ).replace(
                            "\\",
                            "/",
                        ),
                        "line": index,
                        "text": line[:1000],
                    }
                )

                if len(results) >= MAX_SEARCH_RESULTS:
                    break

    return results


# ============================================================
# PROJECT TEST STRATEGY
# ============================================================

def test_commands(
    project: Dict[str, Any],
    workspace: Path,
) -> List[List[str]]:

    ptype = project.get(
        "type",
        "unknown",
    )

    commands: List[List[str]] = []

    if ptype == "python":

        if (workspace / "pytest.ini").exists() \
                or (workspace / "pyproject.toml").exists() \
                or (workspace / "tests").exists():

            commands.append(
                [
                    "python",
                    "-m",
                    "pytest",
                ]
            )

    elif ptype == "node":

        package_json = workspace / "package.json"

        if package_json.exists():

            try:
                package = json.loads(
                    package_json.read_text(
                        encoding="utf-8"
                    )
                )

                scripts = package.get(
                    "scripts",
                    {},
                )

                if "test" in scripts:
                    commands.append(
                        [
                            "npm",
                            "test",
                            "--",
                            "--runInBand",
                        ]
                    )

            except Exception:
                pass

    elif ptype == "go":

        commands.append(
            [
                "go",
                "test",
                "./...",
            ]
        )

    elif ptype == "rust":

        commands.append(
            [
                "cargo",
                "test",
            ]
        )

    elif ptype == "java-maven":

        commands.append(
            [
                "./mvnw",
                "test",
            ]
            if (workspace / "mvnw").exists()
            else [
                "mvn",
                "test",
            ]
        )

    elif ptype == "java-gradle":

        commands.append(
            [
                "./gradlew",
                "test",
            ]
            if (workspace / "gradlew").exists()
            else [
                "gradle",
                "test",
            ]
        )

    return commands


def build_commands(
    project: Dict[str, Any],
    workspace: Path,
) -> List[List[str]]:

    ptype = project.get(
        "type",
        "unknown",
    )

    if ptype == "node":

        package_json = workspace / "package.json"

        if package_json.exists():

            try:
                package = json.loads(
                    package_json.read_text(
                        encoding="utf-8"
                    )
                )

                scripts = package.get(
                    "scripts",
                    {},
                )

                if "build" in scripts:
                    return [
                        [
                            "npm",
                            "run",
                            "build",
                        ]
                    ]

            except Exception:
                pass

    return []


def typecheck_commands(
    project: Dict[str, Any],
    workspace: Path,
) -> List[List[str]]:

    ptype = project.get(
        "type",
        "unknown",
    )

    if ptype == "node":

        package_json = workspace / "package.json"

        if package_json.exists():

            try:
                package = json.loads(
                    package_json.read_text(
                        encoding="utf-8"
                    )
                )

                scripts = package.get(
                    "scripts",
                    {},
                )

                if "typecheck" in scripts:
                    return [
                        [
                            "npm",
                            "run",
                            "typecheck",
                        ]
                    ]

                if (
                    (workspace / "tsconfig.json").exists()
                ):
                    return [
                        [
                            "npx",
                            "tsc",
                            "--noEmit",
                        ]
                    ]

            except Exception:
                pass

    return []


# ============================================================
# AGENT CONTEXT
# ============================================================

def workspace_context(
    session: AgentSession,
) -> Dict[str, Any]:

    if not session.workspace:
        return {}

    return {
        "session_id": session.id,
        "mode": session.mode,
        "authorized": session.authorized,
        "repository": session.repository,
        "project": session.project,
        "tree": list_tree(
            session.workspace,
            max_items=1000,
        ),
        "git_status": git_status(
            session.workspace
        ),
    }


# ============================================================
# AGENT ACTION EXECUTION
# ============================================================

def execute_agent_action(
    session: AgentSession,
    action: Dict[str, Any],
) -> Dict[str, Any]:

    name = action.get("action")

    if not name:
        return {
            "ok": False,
            "error": "Missing action.",
        }

    workspace = session.workspace

    if not workspace:
        return {
            "ok": False,
            "error": "No active workspace.",
        }

    # --------------------------------------------------------
    # LIST FILES
    # --------------------------------------------------------

    if name == "list_files":

        return {
            "ok": True,
            "files": list_tree(
                workspace
            ),
        }

    # --------------------------------------------------------
    # READ FILE
    # --------------------------------------------------------

    if name == "read_file":

        path = safe_path(
            session,
            action.get("path", ""),
        )

        try:
            content = read_file(path)

            return {
                "ok": True,
                "path": action.get("path"),
                "content": content,
            }

        except Exception as exc:

            return {
                "ok": False,
                "error": str(exc),
            }

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if name == "search_files":

        query = str(
            action.get("query", "")
        )

        return {
            "ok": True,
            "results": search_files(
                workspace,
                query,
            ),
        }

    # --------------------------------------------------------
    # WRITE FILE
    # --------------------------------------------------------

    if name == "write_file":

        path = safe_path(
            session,
            action.get("path", ""),
        )

        content = action.get(
            "content",
            "",
        )

        if not isinstance(content, str):
            return {
                "ok": False,
                "error": "content must be a string.",
            }

        if len(content.encode("utf-8")) > MAX_FILE_SIZE:
            return {
                "ok": False,
                "error": "File exceeds MAX_FILE_SIZE.",
            }

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            content,
            encoding="utf-8",
        )

        return {
            "ok": True,
            "action": "write_file",
            "path": action.get("path"),
        }

    # --------------------------------------------------------
    # DELETE FILE
    # --------------------------------------------------------

    if name == "delete_file":

        path = safe_path(
            session,
            action.get("path", ""),
        )

        if not path.exists():
            return {
                "ok": False,
                "error": "File does not exist.",
            }

        if path.is_dir():
            return {
                "ok": False,
                "error": (
                    "Directory deletion is disabled "
                    "for agent safety."
                ),
            }

        path.unlink()

        return {
            "ok": True,
            "action": "delete_file",
            "path": action.get("path"),
        }

    # --------------------------------------------------------
    # GIT STATUS
    # --------------------------------------------------------

    if name == "git_status":

        return git_status(workspace)

    # --------------------------------------------------------
    # GIT DIFF
    # --------------------------------------------------------

    if name == "git_diff":

        return git_diff(workspace)

    # --------------------------------------------------------
    # TEST
    # --------------------------------------------------------

    if name == "run_test":

        commands = test_commands(
            session.project or {},
            workspace,
        )

        if not commands:
            return {
                "ok": True,
                "skipped": True,
                "reason": (
                    "No automatic test command "
                    "was detected."
                ),
            }

        command = commands[0]

        result = run_process(
            command,
            workspace,
            timeout=COMMAND_TIMEOUT,
        )

        session.test_iterations += 1

        return {
            **result,
            "operation": "test",
        }

    # --------------------------------------------------------
    # BUILD
    # --------------------------------------------------------

    if name == "run_build":

        commands = build_commands(
            session.project or {},
            workspace,
        )

        if not commands:
            return {
                "ok": True,
                "skipped": True,
                "reason": (
                    "No automatic build command "
                    "was detected."
                ),
            }

        return {
            **run_process(
                commands[0],
                workspace,
                timeout=COMMAND_TIMEOUT,
            ),
            "operation": "build",
        }

    # --------------------------------------------------------
    # TYPECHECK
    # --------------------------------------------------------

    if name == "run_typecheck":

        commands = typecheck_commands(
            session.project or {},
            workspace,
        )

        if not commands:
            return {
                "ok": True,
                "skipped": True,
                "reason": (
                    "No automatic typecheck "
                    "command was detected."
                ),
            }

        return {
            **run_process(
                commands[0],
                workspace,
                timeout=COMMAND_TIMEOUT,
            ),
            "operation": "typecheck",
        }

    # --------------------------------------------------------
    # COMMAND
    # --------------------------------------------------------

    if name == "run_command":

        command = action.get("command")

        if not isinstance(command, list):
            return {
                "ok": False,
                "error": (
                    "run_command requires command "
                    "as an array."
                ),
            }

        if not command:
            return {
                "ok": False,
                "error": "Empty command.",
            }

        # Prevent obvious secret/environment exfiltration.
        joined = " ".join(
            str(x)
            for x in command
        ).lower()

        forbidden_patterns = [
            "github_token",
            "openrouter_api_key",
            "openai_api_key",
            "printenv",
            "env",
        ]

        if any(
            pattern in joined
            for pattern in forbidden_patterns
        ):
            return {
                "ok": False,
                "error": (
                    "Command blocked because it "
                    "may expose secrets."
                ),
            }

        return run_process(
            [
                str(x)
                for x in command
            ],
            workspace,
            timeout=COMMAND_TIMEOUT,
        )

    # --------------------------------------------------------
    # FINISH
    # --------------------------------------------------------

    if name == "finish":

        return {
            "ok": True,
            "finished": True,
            "summary": action.get(
                "summary",
                "Work completed.",
            ),
        }

    return {
        "ok": False,
        "error": (
            f"Unknown agent action: {name}"
        ),
    }


# ============================================================
# AI ACTION PLANNER
# ============================================================

def agent_action_prompt(
    session: AgentSession,
    task: str,
    history: List[Dict[str, Any]],
) -> str:

    context = workspace_context(
        session
    )

    recent_history = history[-12:]

    return f"""
You are operating Open Agent Work Mode.

USER TASK:
{task}

CURRENT BACKEND CAPABILITIES:
{json.dumps(CAPABILITIES, indent=2)}

CURRENT SESSION:
{json.dumps(
    {
        "id": session.id,
        "authorized": session.authorized,
        "project": session.project,
        "repository": session.repository,
        "iterations": session.iterations,
        "test_iterations": session.test_iterations,
    },
    indent=2,
)}

CURRENT WORKSPACE CONTEXT:
{json.dumps(
    context,
    indent=2,
    default=str,
)}

RECENT AGENT HISTORY:
{json.dumps(
    recent_history,
    indent=2,
    default=str,
)}

AVAILABLE ACTIONS:

1. list_files
2. read_file
3. search_files
4. write_file
5. delete_file
6. git_status
7. git_diff
8. run_test
9. run_build
10. run_typecheck
11. run_command
12. finish

ACTION FORMAT:

Return ONLY valid JSON.

Examples:

{{"action":"list_files"}}

{{"action":"read_file","path":"src/main.py"}}

{{"action":"search_files","query":"login"}}

{{"action":"write_file","path":"src/main.py","content":"..."}}

{{"action":"delete_file","path":"old.js"}}

{{"action":"run_test"}}

{{"action":"run_build"}}

{{"action":"run_typecheck"}}

{{"action":"run_command","command":["npm","install"]}}

{{"action":"git_status"}}

{{"action":"git_diff"}}

{{"action":"finish","summary":"Implemented and verified the requested changes."}}

RULES:

- Inspect before editing.
- Read relevant files before changing them.
- Use multiple files when necessary.
- Do not rewrite unrelated files.
- Do not fabricate results.
- After modifications, inspect git diff.
- Run appropriate tests.
- If tests fail, diagnose and fix.
- Retest after fixes.
- Use build/typecheck when relevant.
- Do not finish immediately after a failed test.
- Stay inside the active workspace.
- Never expose secrets.
- Do not return markdown.
- Return exactly one JSON action.
"""


# ============================================================
# AUTONOMOUS WORK LOOP
# ============================================================

def autonomous_worker(
    session: AgentSession,
    task: str,
) -> None:

    session.started_at = time.time()
    session.status = "working"
    session.cancelled = False
    session.task = task

    log_event(
        session,
        "work_started",
        "Open Agent started autonomous work.",
    )

    history: List[Dict[str, Any]] = []

    started = time.time()

    try:

        while (
            session.iterations
            < MAX_AGENT_ITERATIONS
        ):

            if session.cancelled:
                session.status = "stopped"

                log_event(
                    session,
                    "work_stopped",
                    "Work stopped by user.",
                )

                return

            if (
                time.time() - started
                > WORKSPACE_TIMEOUT
            ):
                session.status = "failed"

                log_event(
                    session,
                    "timeout",
                    "Maximum work session timeout reached.",
                )

                return

            session.iterations += 1

            log_event(
                session,
                "agent_iteration",
                f"Agent iteration {session.iterations}",
                {
                    "iteration": session.iterations,
                },
            )

            prompt = agent_action_prompt(
                session,
                task,
                history,
            )

            try:

                response = asyncio.run(
                    work_ai_service.text(
                        prompt,
                        system=AGENT_SYSTEM_PROMPT,
                        temperature=0.15,
                    )
                )

            except Exception as exc:

                log_event(
                    session,
                    "ai_error",
                    str(exc),
                )

                session.status = "failed"
                return

            action = extract_json(response)

            if not isinstance(action, dict):

                log_event(
                    session,
                    "invalid_action",
                    "AI returned invalid action JSON.",
                    {
                        "response": response[:5000],
                    },
                )

                history.append(
                    {
                        "type": "error",
                        "error": (
                            "Invalid JSON action "
                            "returned by AI."
                        ),
                    }
                )

                continue

            action_name = action.get(
                "action",
                "unknown",
            )

            log_event(
                session,
                "agent_action",
                f"Executing {action_name}",
                {
                    "action": action_name,
                },
            )

            result = execute_agent_action(
                session,
                action,
            )

            # Never expose potentially sensitive
            # command arguments or environment data.
            safe_result = dict(result)

            history.append(
                {
                    "action": action,
                    "result": safe_result,
                }
            )

            log_event(
                session,
                "action_result",
                f"{action_name} completed.",
                {
                    "ok": result.get("ok"),
                    "operation": result.get(
                        "operation"
                    ),
                    "returncode": result.get(
                        "returncode"
                    ),
                    "stdout": result.get(
                        "stdout",
                        "",
                    )[-10000:],
                    "stderr": result.get(
                        "stderr",
                        "",
                    )[-10000:],
                },
            )

            # ------------------------------------------------
            # TEST FAILURE
            # ------------------------------------------------

            if (
                action_name in {
                    "run_test",
                    "run_build",
                    "run_typecheck",
                    "run_command",
                }
                and result.get("ok") is False
            ):

                if (
                    session.test_iterations
                    >= MAX_TEST_ITERATIONS
                ):

                    log_event(
                        session,
                        "test_limit",
                        (
                            "Maximum test/fix "
                            "iterations reached."
                        ),
                    )

                    # Let AI make final assessment.
                    history.append(
                        {
                            "type": "test_limit",
                            "message": (
                                "Maximum test iterations "
                                "reached."
                            ),
                        }
                    )

                else:

                    log_event(
                        session,
                        "error_detected",
                        (
                            "Failure detected. "
                            "Agent should diagnose and fix."
                        ),
                        {
                            "stderr": result.get(
                                "stderr",
                                "",
                            )[-10000:],
                        },
                    )

            # ------------------------------------------------
            # FINISH
            # ------------------------------------------------

            if (
                action_name == "finish"
                and result.get("finished")
            ):

                log_event(
                    session,
                    "final_review",
                    "Running final git status and diff.",
                )

                final_status = git_status(
                    session.workspace
                )

                final_diff = git_diff(
                    session.workspace
                )

                log_event(
                    session,
                    "final_state",
                    "Final workspace state collected.",
                    {
                        "git_status": final_status,
                        "git_diff": final_diff,
                    },
                )

                session.status = "completed"
                session.finished_at = time.time()

                log_event(
                    session,
                    "work_completed",
                    result.get(
                        "summary",
                        "Work completed.",
                    ),
                )

                # Optional automatic push.
                if AUTO_PUSH and GITHUB_TOKEN:

                    log_event(
                        session,
                        "auto_push",
                        "AUTO_PUSH is enabled. Pushing changes.",
                    )

                    push_result = git_push(
                        session.workspace
                    )

                    log_event(
                        session,
                        "push_result",
                        (
                            "Automatic push completed."
                            if push_result.get("ok")
                            else "Automatic push failed."
                        ),
                        {
                            "ok": push_result.get(
                                "ok"
                            ),
                            "stderr": push_result.get(
                                "stderr",
                                "",
                            )[-10000:],
                            "stdout": push_result.get(
                                "stdout",
                                "",
                            )[-10000:],
                        },
                    )

                return

        session.status = "failed"

        log_event(
            session,
            "iteration_limit",
            (
                "Maximum autonomous agent "
                "iterations reached."
            ),
        )

    except Exception as exc:

        session.status = "failed"

        log_event(
            session,
            "worker_exception",
            str(exc),
            {
                "traceback": traceback.format_exc()[
                    -10000:
                ]
            },
        )

    finally:

        session.finished_at = time.time()


# ============================================================
# CHAT
# ============================================================

async def process_chat(
    message: str,
) -> str:

    prompt = f"""
User message:

{message}

Respond naturally and helpfully.

You are Open Agent.

If the user asks what you can do, explain your real backend
capabilities based on the capability specification.

Do not falsely claim repository access unless the backend
capability/session provides it.

Do not claim that code was changed unless Work Mode actually
performed the operation.

Do not claim tests passed unless actual test output confirms it.
"""

    return await ai_service.text(
        prompt,
        system=AGENT_SYSTEM_PROMPT,
        temperature=0.35,
    )


@app.post("/chat")
async def chat(
    request: Request,
):
    """
    Compatible with both:

    JSON:
        {"message":"Hi"}

    and:

        application/x-www-form-urlencoded
        message=Hi
    """

    content_type = (
        request.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    message: Optional[str] = None

    try:

        if "application/json" in content_type:

            body = await request.json()

            if isinstance(body, dict):
                message = body.get(
                    "message"
                )

        elif (
            "application/x-www-form-urlencoded"
            in content_type
            or "multipart/form-data"
            in content_type
        ):

            form = await request.form()

            message = form.get(
                "message"
            )

        else:

            # Graceful fallback.
            try:

                body = await request.json()

                if isinstance(body, dict):
                    message = body.get(
                        "message"
                    )

            except Exception:

                try:

                    form = await request.form()

                    message = form.get(
                        "message"
                    )

                except Exception:
                    pass

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=f"Invalid request body: {exc}",
        )

    if not message or not str(message).strip():

        raise HTTPException(
            status_code=422,
            detail="message is required",
        )

    reply = await process_chat(
        str(message).strip()
    )

    return {
        "ok": True,
        "reply": reply,
    }


# ============================================================
# PLAN MODE
# ============================================================

@app.post("/plan")
async def create_plan(
    request: PlanRequest,
):

    session = create_session(
        mode="plan"
    )

    session.mode = "plan"

    context = request.context or ""

    prompt = f"""
Create a professional software implementation plan.

USER REQUIREMENT:
{request.message}

ADDITIONAL CONTEXT:
{context}

The plan must include:

1. Understanding
2. Goals
3. Relevant project areas
4. Files likely to change
5. Implementation steps
6. Multi-file considerations
7. Testing strategy
8. Build/typecheck strategy
9. Risks
10. Definition of done

Do NOT modify files.

Return a clear human-readable plan.
"""

    plan = await ai_service.text(
        prompt,
        system=AGENT_SYSTEM_PROMPT,
        temperature=0.25,
    )

    session.plan = plan
    session.task = request.message
    session.status = "planned"

    log_event(
        session,
        "plan_created",
        "Implementation plan created.",
    )

    return {
        "ok": True,
        "session_id": session.id,
        "mode": "plan",
        "plan": plan,
        "finalized": False,
    }


# ============================================================
# FINALIZE PLAN
# ============================================================

@app.post("/plan/finalize")
async def finalize_plan(
    request: FinalizePlanRequest,
):

    session = get_session(
        request.session_id
    )

    if session.mode != "plan":
        raise HTTPException(
            status_code=400,
            detail=(
                "Only Plan Mode sessions "
                "can be finalized."
            ),
        )

    if request.plan:
        session.plan = request.plan

    if not session.plan:
        raise HTTPException(
            status_code=400,
            detail="No plan exists.",
        )

    session.plan_finalized = True
    session.authorized = False
    session.status = "plan_finalized"

    log_event(
        session,
        "plan_finalized",
        (
            "Plan finalized. "
            "Work authorization is still required."
        ),
    )

    return {
        "ok": True,
        "session_id": session.id,
        "plan": session.plan,
        "finalized": True,
        "work_authorized": False,
        "requires_authorization": True,
    }


# ============================================================
# REPOSITORY INSPECT
# ============================================================

@app.post("/repository/inspect")
async def repository_inspect(
    request: RepoRequest,
):

    session = create_session(
        mode="repository"
    )

    workspace = (
        WORKSPACE_ROOT
        / session.id
        / "repo"
    )

    result = clone_repo(
        request.repository_url,
        request.branch,
        workspace,
    )

    session.workspace = workspace
    session.repository = {
        "url": request.repository_url,
        "branch": request.branch,
    }

    session.project = detect_project(
        workspace
    )

    session.status = "ready"

    return {
        "ok": True,
        "session_id": session.id,
        "repository": session.repository,
        "project": session.project,
        "tree": list_tree(workspace),
    }


# ============================================================
# READ FILE
# ============================================================

@app.post("/repository/read")
async def repository_read(
    request: ReadFileRequest,
):

    session = get_session(
        request.session_id
    )

    path = safe_path(
        session,
        request.path,
    )

    try:

        return {
            "ok": True,
            "path": request.path,
            "content": read_file(path),
        }

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# SEARCH
# ============================================================

@app.post("/repository/search")
async def repository_search(
    request: SearchRequest,
):

    session = get_session(
        request.session_id
    )

    if not session.workspace:
        raise HTTPException(
            status_code=400,
            detail="No workspace.",
        )

    return {
        "ok": True,
        "query": request.query,
        "results": search_files(
            session.workspace,
            request.query,
        ),
    }


# ============================================================
# DIRECT FILE EDIT
# ============================================================

@app.post("/repository/edit")
async def repository_edit(
    request: EditFileRequest,
):

    session = get_session(
        request.session_id
    )

    if not session.authorized:
        raise HTTPException(
            status_code=403,
            detail=(
                "File modification requires "
                "an authorized Work Mode session."
            ),
        )

    path = safe_path(
        session,
        request.path,
    )

    if len(
        request.content.encode("utf-8")
    ) > MAX_FILE_SIZE:

        raise HTTPException(
            status_code=413,
            detail="File too large.",
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        request.content,
        encoding="utf-8",
    )

    return {
        "ok": True,
        "path": request.path,
        "modified": True,
    }


# ============================================================
# ZIP UPLOAD
# ============================================================

@app.post("/project/upload")
async def project_upload(
    file: UploadFile = File(...),
):

    session = create_session(
        mode="zip"
    )

    destination = (
        WORKSPACE_ROOT
        / session.id
        / "project"
    )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    if not file.filename.lower().endswith(
        ".zip"
    ):
        raise HTTPException(
            status_code=400,
            detail="Only ZIP files are supported.",
        )

    zip_path = (
        UPLOAD_ROOT
        / f"{session.id}.zip"
    )

    data = await file.read(MAX_UPLOAD_SIZE + 1)

    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"ZIP file exceeds the {MAX_UPLOAD_SIZE} byte limit.",
        )

    zip_path.write_bytes(data)

    try:

        with zipfile.ZipFile(
            zip_path,
            "r",
        ) as archive:

            members = archive.infolist()
            if len(members) > MAX_ZIP_FILES:
                raise HTTPException(status_code=413, detail="ZIP contains too many files.")

            total_uncompressed = 0
            for member in members:

                total_uncompressed += member.file_size
                if total_uncompressed > MAX_ZIP_UNCOMPRESSED_SIZE:
                    raise HTTPException(status_code=413, detail="ZIP expands beyond the allowed size.")

                mode = (member.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise HTTPException(status_code=400, detail="Symbolic links are not allowed in ZIP files.")

                member_path = (
                    destination
                    / member.filename
                ).resolve()

                try:
                    member_path.relative_to(
                        destination.resolve()
                    )
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Unsafe ZIP path detected."
                        ),
                    )

                if member.is_dir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue

                member_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, member_path.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)

    except zipfile.BadZipFile:

        raise HTTPException(
            status_code=400,
            detail="Invalid ZIP file.",
        )

    session.workspace = destination
    session.project = detect_project(
        destination
    )
    session.status = "uploaded"

    return {
        "ok": True,
        "session_id": session.id,
        "project": session.project,
        "tree": list_tree(destination),
    }


# ============================================================
# DOWNLOAD PROJECT
# ============================================================

@app.get("/project/download/{session_id}")
async def project_download(
    session_id: str,
):

    session = get_session(
        session_id
    )

    if not session.workspace:
        raise HTTPException(
            status_code=400,
            detail="No workspace.",
        )

    output = (
        EXPORT_ROOT
        / f"{session.id}.zip"
    )

    if output.exists():
        output.unlink()

    with zipfile.ZipFile(
        output,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:

        for path in session.workspace.rglob("*"):

            if not path.is_file():
                continue

            if ".git" in path.parts:
                continue

            archive.write(
                path,
                path.relative_to(
                    session.workspace
                ),
            )

    return FileResponse(
        output,
        filename=f"open-agent-{session.id}.zip",
        media_type="application/zip",
    )


# ============================================================
# WORK PREPARE
# ============================================================

@app.post("/work/prepare")
async def work_prepare(
    request: WorkPrepareRequest,
):

    if not request.authorization:
        raise HTTPException(
            status_code=403,
            detail=(
                "Explicit Work Mode authorization "
                "is required."
            ),
        )

    # Existing plan session.
    if request.session_id:

        session = get_session(
            request.session_id
        )

        if (
            session.mode == "plan"
            and not session.plan_finalized
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Plan must be finalized "
                    "before Work Mode."
                ),
            )

    else:

        session = create_session(
            mode="work"
        )

    session.mode = "work"
    session.authorized = True
    session.cancelled = False

    # Clone repository if provided.
    if request.repository_url:

        workspace = (
            WORKSPACE_ROOT
            / session.id
            / "repo"
        )

        clone_repo(
            request.repository_url,
            request.branch,
            workspace,
        )

        session.workspace = workspace

        session.repository = {
            "url": request.repository_url,
            "branch": request.branch,
        }

    elif not session.workspace:

        raise HTTPException(
            status_code=400,
            detail=(
                "Provide repository_url or use "
                "an existing uploaded workspace."
            ),
        )

    session.project = detect_project(
        session.workspace
    )

    session.status = "prepared"

    log_event(
        session,
        "work_authorized",
        (
            "User explicitly authorized "
            "Work Mode."
        ),
    )

    return {
        "ok": True,
        "session_id": session.id,
        "mode": "work",
        "authorized": True,
        "status": session.status,
        "repository": session.repository,
        "project": session.project,
        "tree": list_tree(
            session.workspace
        ),
    }


# ============================================================
# WORK EXECUTE
# ============================================================

@app.post("/work/execute")
async def work_execute(
    request: WorkExecuteRequest,
):

    session = get_session(
        request.session_id
    )

    if not session.authorized:
        raise HTTPException(
            status_code=403,
            detail=(
                "Work Mode is not authorized."
            ),
        )

    if not session.workspace:
        raise HTTPException(
            status_code=400,
            detail="No workspace.",
        )

    if session.status in {
        "working",
        "testing",
        "fixing",
    }:

        return {
            "ok": True,
            "already_running": True,
            "session_id": session.id,
        }

    task = (
        request.task
        or session.task
        or session.plan
    )

    if not task:
        raise HTTPException(
            status_code=422,
            detail="task is required.",
        )

    session.task = task
    session.status = "queued"
    session.cancelled = False

    thread = threading.Thread(
        target=autonomous_worker,
        args=(session, task),
        daemon=True,
    )

    thread.start()

    return {
        "ok": True,
        "session_id": session.id,
        "status": "queued",
        "message": (
            "Autonomous Work Mode started."
        ),
    }


# ============================================================
# WORK STOP
# ============================================================

@app.post("/work/stop")
async def work_stop(
    request: SessionRequest,
):

    session = get_session(
        request.session_id
    )

    session.cancelled = True
    session.status = "stopping"

    log_event(
        session,
        "stop_requested",
        "Stop requested by user.",
    )

    return {
        "ok": True,
        "session_id": session.id,
        "status": "stopping",
    }


# ============================================================
# WORK STATUS
# ============================================================

@app.get("/work/status/{session_id}")
async def work_status(
    session_id: str,
):

    session = get_session(
        session_id
    )

    with session.lock:

        return {
            "ok": True,
            "session_id": session.id,
            "mode": session.mode,
            "status": session.status,
            "authorized": session.authorized,
            "plan_finalized": session.plan_finalized,
            "task": session.task,
            "iterations": session.iterations,
            "test_iterations": (
                session.test_iterations
            ),
            "started_at": session.started_at,
            "finished_at": session.finished_at,
        }


# ============================================================
# WORK LOGS
# ============================================================

@app.get("/work/logs/{session_id}")
async def work_logs(
    session_id: str,
):

    session = get_session(
        session_id
    )

    with session.lock:

        return {
            "ok": True,
            "session_id": session.id,
            "status": session.status,
            "logs": list(session.logs),
        }


# ============================================================
# COMMIT
# ============================================================

@app.post("/work/commit")
async def work_commit(
    request: CommitRequest,
):

    session = get_session(
        request.session_id
    )

    if not session.authorized:
        raise HTTPException(
            status_code=403,
            detail="Work authorization required.",
        )

    if not session.workspace:
        raise HTTPException(
            status_code=400,
            detail="No workspace.",
        )

    message = (
        request.message
        or "Open Agent: implement requested changes"
    )

    result = git_commit(
        session.workspace,
        message,
    )

    log_event(
        session,
        "commit",
        (
            "Commit successful."
            if result.get("ok")
            else "Commit failed."
        ),
        {
            "ok": result.get("ok"),
            "stdout": result.get(
                "stdout",
                "",
            )[-10000:],
            "stderr": result.get(
                "stderr",
                "",
            )[-10000:],
        },
    )

    return {
        "ok": result.get("ok"),
        "message": (
            "Commit successful."
            if result.get("ok")
            else "Commit failed."
        ),
        "result": result,
    }


# ============================================================
# PUSH
# ============================================================

@app.post("/work/push")
async def work_push(
    request: PushRequest,
):

    session = get_session(
        request.session_id
    )

    if not session.authorized:
        raise HTTPException(
            status_code=403,
            detail="Work authorization required.",
        )

    if not GITHUB_TOKEN:
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub push capability is unavailable "
                "because GITHUB_TOKEN is not configured."
            ),
        )

    if not session.workspace:
        raise HTTPException(
            status_code=400,
            detail="No workspace.",
        )

    result = git_push(
        session.workspace,
        request.branch,
    )

    log_event(
        session,
        "push",
        (
            "Push successful."
            if result.get("ok")
            else "Push failed."
        ),
        {
            "ok": result.get("ok"),
            "stdout": result.get(
                "stdout",
                "",
            )[-10000:],
            "stderr": result.get(
                "stderr",
                "",
            )[-10000:],
        },
    )

    return {
        "ok": result.get("ok"),
        "message": (
            "Successfully pushed to GitHub."
            if result.get("ok")
            else "GitHub push failed."
        ),
        "result": result,
    }


# ============================================================
# SIMPLE DOWNLOAD ENDPOINT
# ============================================================

@app.get("/download/{filename}")
async def download_file(
    filename: str,
):

    # Only allow files from EXPORT_ROOT.
    candidate = (
        EXPORT_ROOT
        / filename
    ).resolve()

    try:
        candidate.relative_to(
            EXPORT_ROOT.resolve()
        )
    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid filename.",
        )

    if not candidate.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    return FileResponse(
        candidate,
        filename=candidate.name,
    )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():

    cleanup_expired_sessions()

    return {
        "ok": True,
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "online",

        "ai": {
            "provider": "Gemini",
            "configured": ai_service.available(),
            "available": ai_service.available(),
            "model": chat_plan_router.providers[0].chat_model,
        },

        "github": {
            "configured": bool(
                GITHUB_TOKEN
            ),
        },

        "capabilities": CAPABILITIES,

        "limits": {
            "max_agent_iterations": (
                MAX_AGENT_ITERATIONS
            ),
            "max_test_iterations": (
                MAX_TEST_ITERATIONS
            ),
            "command_timeout": (
                COMMAND_TIMEOUT
            ),
            "workspace_timeout": (
                WORKSPACE_TIMEOUT
            ),
            "max_file_size": MAX_FILE_SIZE,
            "max_upload_size": MAX_UPLOAD_SIZE,
            "max_zip_files": MAX_ZIP_FILES,
            "max_zip_uncompressed_size": MAX_ZIP_UNCOMPRESSED_SIZE,
            "session_ttl": SESSION_TTL,
        },

        "modes": {
            "chat": True,
            "plan": True,
            "work": True,
        },
    }


@app.get("/ai/providers")
async def ai_providers():
    return {
        "providers": chat_plan_router.status() + [
            {
                "name": "mini-SWE-agent",
                "purpose": ["work", "coding"],
                "configured": ai_router.available(),
                "available": ai_router.available(),
                "model": ai_router.providers[0].model,
            }
        ],
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():

    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": (
            "Advanced autonomous AI "
            "software engineering agent."
        ),
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
        "modes": [
            "chat",
            "plan",
            "work",
        ],
    }


# ============================================================
# GLOBAL ERROR HANDLER
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
):

    # Do not expose secrets or full environment.
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": "Internal server error.",
        },
    )


# ============================================================
# LOCAL ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        )
