"""
Open Agent - Advanced SWE Agent Backend

Features:
- ChatGPT-like Chat Mode
- Plan Mode
- Work Mode authorization
- Gemini 2.5 Flash
- GitHub repository clone/read/search/edit
- Multi-file coding loop
- Automatic testing
- Automatic error -> diagnosis -> fix loop
- Git diff/status
- Explicit /work/commit
- Explicit /work/push
- Automatic commit/push support
- ZIP upload/download
- JSON + form request compatibility
- Session/workspace isolation
- Sensitive-file protection
- Command timeout/output limits
- CORS support
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
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
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

APP_NAME = "Open Agent"
APP_VERSION = "2.0.0"

BASE_DIR = Path(
    os.getenv("WORKSPACE_ROOT", "/tmp/open-agent")
).resolve()

BASE_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash",
)

MAX_AGENT_ITERATIONS = int(
    os.getenv("MAX_AGENT_ITERATIONS", "30")
)

MAX_ERROR_FIX_ITERATIONS = int(
    os.getenv("MAX_ERROR_FIX_ITERATIONS", "8")
)

MAX_FILE_SIZE = int(
    os.getenv("MAX_FILE_SIZE", "3000000")
)

MAX_COMMAND_OUTPUT = int(
    os.getenv("MAX_COMMAND_OUTPUT", "120000")
)

COMMAND_TIMEOUT = int(
    os.getenv("COMMAND_TIMEOUT", "180")
)

ARCHIVE_MAX_SIZE = int(
    os.getenv("ARCHIVE_MAX_SIZE", "300000000")
)

AUTO_PUSH = os.getenv(
    "AUTO_PUSH",
    "false",
).lower() == "true"

AUTO_COMMIT = os.getenv(
    "AUTO_COMMIT",
    "false",
).lower() == "true"

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger(APP_NAME)


# ============================================================
# PROTECTED FILES
# ============================================================

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}

SENSITIVE_PARTS = (
    "password",
    "secret",
    "credential",
    "private_key",
    "access_token",
)

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


# ============================================================
# SAFE TEST COMMANDS
# ============================================================

PYTHON_TEST_COMMANDS = [
    ["python", "-m", "pytest"],
    ["pytest"],
]

NODE_TEST_COMMANDS = [
    ["npm", "test"],
]

NODE_BUILD_COMMANDS = [
    ["npm", "run", "build"],
]

TYPECHECK_COMMANDS = [
    ["npm", "run", "typecheck"],
    ["npx", "tsc", "--noEmit"],
]

GO_TEST_COMMANDS = [
    ["go", "test", "./..."],
]

RUST_TEST_COMMANDS = [
    ["cargo", "test"],
]

JAVA_TEST_COMMANDS = [
    ["mvn", "test"],
]


# ============================================================
# HELPERS
# ============================================================

def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: str) -> str:
    """
    Remove configured secrets from logs/responses.
    """

    if not isinstance(value, str):
        return value

    secrets = [
        os.getenv("GITHUB_TOKEN"),
        os.getenv("GEMINI_API_KEY"),
    ]

    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")

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


def context_to_text(context: Any) -> str:

    if context is None:
        return ""

    if isinstance(context, str):
        return context

    try:
        return json.dumps(
            context,
            ensure_ascii=False,
        )
    except Exception:
        return str(context)


# ============================================================
# REQUEST COMPATIBILITY
# ============================================================

async def read_request_data(request: Request) -> dict[str, Any]:
    """
    Accept both:
      application/json
      application/x-www-form-urlencoded
      multipart/form-data
    """

    content_type = (
        request.headers.get("content-type", "")
        .lower()
    )

    try:

        if "application/json" in content_type:

            data = await request.json()

            if not isinstance(data, dict):
                raise api_error(
                    "INVALID_REQUEST",
                    "JSON body must be an object.",
                )

            return data

        form = await request.form()

        return {
            str(k): v
            for k, v in form.items()
        }

    except HTTPException:
        raise

    except Exception as exc:

        logger.warning(
            "Request parsing failed: %s",
            redact(str(exc)),
        )

        raise api_error(
            "INVALID_REQUEST_FORMAT",
            "Invalid request format. Send JSON or form data.",
            422,
        )


def required_string(
    data: dict[str, Any],
    key: str,
) -> str:

    value = data.get(key)

    if value is None:
        raise api_error(
            "MISSING_FIELD",
            f"Missing required field: {key}",
            422,
        )

    value = str(value).strip()

    if not value:
        raise api_error(
            "MISSING_FIELD",
            f"Field '{key}' cannot be empty.",
            422,
        )

    return value


# ============================================================
# PATH SECURITY
# ============================================================

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
            "Invalid null character in path.",
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
            "Path must remain inside the repository.",
        )

    if not allow_root and candidate == root:

        raise api_error(
            "INVALID_FILE_PATH",
            "Repository root cannot be used as a file.",
        )

    return candidate


def is_sensitive(
    path: str | Path,
) -> bool:

    parts = [
        p.lower()
        for p in Path(path).parts
    ]

    if not parts:
        return False

    filename = parts[-1]

    if filename in SENSITIVE_NAMES:
        return True

    for part in parts:

        for marker in SENSITIVE_PARTS:

            if marker in part:
                return True

    return False


# ============================================================
# PROCESS EXECUTION
# ============================================================

def run_process(
    args: list[str],
    cwd: Path,
    timeout: int = COMMAND_TIMEOUT,
) -> dict[str, Any]:

    started = time.monotonic()

    try:

        process = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )

        stdout = process.stdout or ""
        stderr = process.stderr or ""

        stdout = stdout[-MAX_COMMAND_OUTPUT:]
        stderr = stderr[-MAX_COMMAND_OUTPUT:]

        return {
            "command": args,
            "stdout": redact(stdout),
            "stderr": redact(stderr),
            "exit_code": process.returncode,
            "success": process.returncode == 0,
            "duration_ms": int(
                (time.monotonic() - started) * 1000
            ),
        }

    except subprocess.TimeoutExpired as exc:

        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode(
                errors="replace"
            )

        if isinstance(stderr, bytes):
            stderr = stderr.decode(
                errors="replace"
            )

        return {
            "command": args,
            "stdout": redact(
                stdout[-MAX_COMMAND_OUTPUT:]
            ),
            "stderr": "Command timed out.",
            "exit_code": -1,
            "success": False,
            "timed_out": True,
            "duration_ms": int(
                (time.monotonic() - started) * 1000
            ),
        }

    except FileNotFoundError:

        return {
            "command": args,
            "stdout": "",
            "stderr": (
                f"Executable not found: {args[0]}"
            ),
            "exit_code": 127,
            "success": False,
            "duration_ms": int(
                (time.monotonic() - started) * 1000
            ),
        }

    except Exception as exc:

        return {
            "command": args,
            "stdout": "",
            "stderr": redact(str(exc)),
            "exit_code": 1,
            "success": False,
            "duration_ms": int(
                (time.monotonic() - started) * 1000
            ),
        }


# ============================================================
# GITHUB
# ============================================================

def parse_github(
    url: str,
) -> tuple[str, str]:

    parsed = urlparse(url)

    if (
        parsed.scheme not in
        {"http", "https"}
    ):
        raise api_error(
            "INVALID_GITHUB_URL",
            "GitHub URL must use HTTP or HTTPS.",
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

    repo = parts[1]

    if repo.endswith(".git"):
        repo = repo[:-4]

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+",
        owner,
    ):
        raise api_error(
            "INVALID_GITHUB_URL",
            "Invalid GitHub owner.",
        )

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+",
        repo,
    ):
        raise api_error(
            "INVALID_GITHUB_URL",
            "Invalid GitHub repository.",
        )

    return owner, repo


def git_environment() -> dict[str, str]:

    env = os.environ.copy()

    token = env.get("GITHUB_TOKEN")

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

    owner, name = parse_github(repo_url)

    if not os.getenv("GITHUB_TOKEN"):

        logger.warning(
            "GITHUB_TOKEN is not configured."
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    process = subprocess.run(
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
        env=git_environment(),
    )

    if process.returncode != 0:

        message = (
            process.stderr
            or process.stdout
            or "Git clone failed."
        )

        message_lower = message.lower()

        if any(
            marker in message_lower
            for marker in [
                "authentication",
                "403",
                "401",
                "repository not found",
                "private",
                "permission",
            ]
        ):

            raise api_error(
                "GITHUB_ACCESS_FAILED",
                "GitHub repository access failed. "
                "Check GITHUB_TOKEN permissions and repository access.",
                401,
            )

        raise api_error(
            "GITHUB_CLONE_FAILED",
            redact(message[-2000:]),
            400,
        )

    commit = run_process(
        ["git", "rev-parse", "HEAD"],
        destination,
    )

    branch = run_process(
        ["git", "branch", "--show-current"],
        destination,
    )

    return {
        "owner": owner,
        "name": name,
        "branch": (
            branch["stdout"].strip()
            or "HEAD"
        ),
        "commit": commit["stdout"].strip(),
    }


# ============================================================
# FILE SYSTEM
# ============================================================

def list_tree(
    root: Path,
    limit: int = 3000,
) -> list[str]:

    result = []

    if not root.exists():
        return result

    for path in sorted(
        root.rglob("*")
    ):

        relative = path.relative_to(root)

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
        raise api_error(
            "SENSITIVE_FILE",
            "Sensitive files cannot be read.",
        )

    if not path.is_file():

        raise api_error(
            "FILE_NOT_FOUND",
            f"File not found: {relative}",
            404,
        )

    if path.stat().st_size > MAX_FILE_SIZE:

        raise api_error(
            "FILE_TOO_LARGE",
            "File exceeds the configured size limit.",
        )

    return path.read_text(
        errors="replace"
    )


def write_file(
    root: Path,
    relative: str,
    content: str,
) -> dict[str, Any]:

    if is_sensitive(relative):

        raise api_error(
            "SENSITIVE_FILE",
            "Sensitive files cannot be modified.",
        )

    if not isinstance(content, str):

        raise api_error(
            "INVALID_CONTENT",
            "File content must be text.",
        )

    if len(content.encode()) > MAX_FILE_SIZE:

        raise api_error(
            "FILE_TOO_LARGE",
            "File exceeds the configured size limit.",
        )

    path = safe_path(
        root,
        relative,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_fd, temporary_path = tempfile.mkstemp(
        prefix=".open-agent-",
        dir=str(path.parent),
    )

    os.close(temporary_fd)

    try:

        Path(
            temporary_path
        ).write_text(
            content,
            encoding="utf-8",
        )

        os.replace(
            temporary_path,
            path,
        )

    finally:

        if os.path.exists(
            temporary_path
        ):
            os.unlink(
                temporary_path
            )

    return {
        "path": relative,
        "bytes": len(
            content.encode()
        ),
        "success": True,
    }


def delete_file(
    root: Path,
    relative: str,
) -> dict[str, Any]:

    path = safe_path(
        root,
        relative,
    )

    if (
        ".git"
        in path.parts
        or is_sensitive(path)
    ):
        raise api_error(
            "PROTECTED_FILE",
            "Protected files cannot be deleted.",
        )

    if not path.is_file():

        raise api_error(
            "FILE_NOT_FOUND",
            "File not found.",
            404,
        )

    path.unlink()

    return {
        "deleted": relative,
        "success": True,
    }


# ============================================================
# PROJECT DETECTION
# ============================================================

def detect_project(
    root: Path,
) -> dict[str, Any]:

    names = {
        p.name
        for p in root.iterdir()
    } if root.exists() else set()

    project_type = "unknown"
    framework = None
    package_manager = None

    test_commands: list[list[str]] = []
    build_commands: list[list[str]] = []
    typecheck_commands: list[list[str]] = []

    if (
        "pyproject.toml" in names
        or "requirements.txt" in names
        or "setup.py" in names
    ):

        project_type = "python"
        package_manager = "pip"
        test_commands = PYTHON_TEST_COMMANDS

    elif "package.json" in names:

        project_type = "node"
        package_manager = "npm"

        try:

            package = json.loads(
                (
                    root / "package.json"
                ).read_text(
                    errors="replace"
                )[:MAX_FILE_SIZE]
            )

            scripts = package.get(
                "scripts",
                {},
            )

            dependencies = {
                **package.get(
                    "dependencies",
                    {},
                ),
                **package.get(
                    "devDependencies",
                    {},
                ),
            }

            if (
                "next" in dependencies
                or any(
                    x.startswith("next.config")
                    for x in names
                )
            ):
                framework = "Next.js"

            elif (
                "vite" in dependencies
                or any(
                    x.startswith("vite.config")
                    for x in names
                )
            ):
                framework = "Vite"

            elif "react" in dependencies:

                framework = "React"

            elif "vue" in dependencies:

                framework = "Vue"

            else:

                framework = "Node.js"

            if "test" in scripts:
                test_commands = [
                    ["npm", "test"]
                ]

            if "build" in scripts:
                build_commands = [
                    ["npm", "run", "build"]
                ]

            if "typecheck" in scripts:
                typecheck_commands = [
                    ["npm", "run", "typecheck"]
                ]

        except Exception:

            pass

    elif "go.mod" in names:

        project_type = "go"
        package_manager = "go"
        test_commands = GO_TEST_COMMANDS

    elif "Cargo.toml" in names:

        project_type = "rust"
        package_manager = "cargo"
        test_commands = RUST_TEST_COMMANDS

    elif "pom.xml" in names:

        project_type = "java"
        package_manager = "maven"
        test_commands = JAVA_TEST_COMMANDS

    return {
        "project_type": project_type,
        "framework": framework,
        "package_manager": package_manager,
        "test_commands": test_commands,
        "build_commands": build_commands,
        "typecheck_commands": typecheck_commands,
        "files": list_tree(root),
    }


# ============================================================
# GIT INFORMATION
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

    diff_stat = run_process(
        [
            "git",
            "diff",
            "--stat",
        ],
        root,
    )

    files_added = []
    files_modified = []
    files_deleted = []

    for line in status["stdout"].splitlines():

        if len(line) < 3:
            continue

        code = line[:2]
        path = line[3:]

        if "D" in code:
            files_deleted.append(path)

        elif (
            "A" in code
            or "?" in code
        ):
            files_added.append(path)

        else:
            files_modified.append(path)

    return {
        "files_added": files_added,
        "files_modified": files_modified,
        "files_deleted": files_deleted,
        "stat": diff_stat["stdout"],
        "clean": not bool(
            files_added
            or files_modified
            or files_deleted
        ),
    }


def full_git_diff(
    root: Path,
) -> str:

    result = run_process(
        [
            "git",
            "diff",
            "--",
            ".",
        ],
        root,
    )

    return result["stdout"]


# ============================================================
# SESSION
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

    last_test: dict[str, Any] | None = None

    def log(
        self,
        level: str,
        kind: str,
        message: str,
        **extra: Any,
    ) -> None:

        entry = {
            "timestamp": now(),
            "level": level,
            "type": kind,
            "message": redact(message),
            **extra,
        }

        self.logs.append(entry)

        getattr(
            logger,
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


SESSIONS: dict[str, Session] = {}


# ============================================================
# WORKSPACE
# ============================================================

def new_workspace(
    session_id: str,
) -> Path:

    if not re.fullmatch(
        r"[A-Za-z0-9_-]{3,80}",
        session_id,
    ):

        raise api_error(
            "INVALID_SESSION_ID",
            "Invalid session_id.",
        )

    workspace = (
        BASE_DIR / session_id
    ).resolve()

    try:

        workspace.relative_to(
            BASE_DIR
        )

    except ValueError:

        raise api_error(
            "WORKSPACE_ERROR",
            "Invalid workspace.",
        )

    if workspace.exists():

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )

    workspace.mkdir(
        parents=True,
        exist_ok=True,
    )

    return workspace


def get_session(
    session_id: str,
) -> Session:

    session = SESSIONS.get(
        session_id
    )

    if not session:

        raise api_error(
            "SESSION_NOT_FOUND",
            "Unknown session_id.",
            404,
        )

    return session


# ============================================================
# GEMINI
# ============================================================

class GeminiService:

    def __init__(self):

        self.client = None

        api_key = os.getenv(
            "GEMINI_API_KEY"
        )

        if (
            genai
            and api_key
        ):

            try:

                self.client = genai.Client(
                    api_key=api_key
                )

            except Exception as exc:

                logger.error(
                    "Gemini initialization failed: %s",
                    redact(str(exc)),
                )

    def generate(
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

        last_error = None

        for attempt in range(5):

            try:

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

                if not text:

                    raise RuntimeError(
                        "Gemini returned empty response."
                    )

                if json_mode:

                    try:

                        return json.loads(text)

                    except json.JSONDecodeError:

                        # Recover JSON wrapped in markdown.
                        match = re.search(
                            r"\{.*\}",
                            text,
                            re.DOTALL,
                        )

                        if match:

                            return json.loads(
                                match.group(0)
                            )

                        raise

                return text

            except Exception as exc:

                last_error = exc

                marker = str(
                    exc
                ).lower()

                temporary = any(
                    x in marker
                    for x in [
                        "429",
                        "503",
                        "unavailable",
                        "resource exhausted",
                        "temporarily",
                        "rate limit",
                        "overloaded",
                    ]
                )

                if (
                    not temporary
                    or attempt == 4
                ):
                    break

                delay = min(
                    12,
                    2 ** attempt,
                )

                time.sleep(delay)

        logger.error(
            "Gemini failed: %s",
            redact(
                str(last_error)
            ),
        )

        raise api_error(
            "AI_TEMPORARILY_UNAVAILABLE",
            "AI model is temporarily unavailable. "
            "Please retry.",
            503,
        )


GEMINI = GeminiService()


# ============================================================
# ACTION EXECUTION
# ============================================================

ALLOWED_ACTIONS = {
    "list_files",
    "read_file",
    "search_files",
    "write_file",
    "delete_file",
    "git_status",
    "git_diff",
    "run_test",
    "run_build",
    "typecheck",
    "git_commit",
    "git_push",
    "finish",
}


def execute_action(
    session: Session,
    action: dict[str, Any],
) -> dict[str, Any]:

    action_name = action.get(
        "action"
    )

    if action_name not in ALLOWED_ACTIONS:

        raise ValueError(
            f"Unsupported action: {action_name}"
        )

    root = (
        session.workspace / "repo"
    )

    if not root.exists():

        raise ValueError(
            "Repository workspace does not exist."
        )

    session.log(
        "info",
        "tool",
        f"Executing {action_name}",
        action=action_name,
    )

    # --------------------------------------------------------
    # LIST
    # --------------------------------------------------------

    if action_name == "list_files":

        return {
            "files": list_tree(root)
        }

    # --------------------------------------------------------
    # READ
    # --------------------------------------------------------

    if action_name == "read_file":

        path = str(
            action.get(
                "path",
                "",
            )
        )

        return {
            "path": path,
            "content": read_file(
                root,
                path,
            ),
        }

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if action_name == "search_files":

        query = str(
            action.get(
                "query",
                "",
            )
        ).strip()

        if not query:

            raise ValueError(
                "Search query is required."
            )

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

            try:

                if (
                    path.stat().st_size
                    > MAX_FILE_SIZE
                ):
                    continue

                text = path.read_text(
                    errors="replace"
                )

                for line_number, line in enumerate(
                    text.splitlines(),
                    1,
                ):

                    if (
                        query.lower()
                        in line.lower()
                    ):

                        matches.append(
                            {
                                "path": relative,
                                "line": line_number,
                                "text": line[:1000],
                            }
                        )

                        if len(matches) >= 300:
                            break

            except OSError:
                continue

            if len(matches) >= 300:
                break

        return {
            "query": query,
            "matches": matches,
        }

    # --------------------------------------------------------
    # WRITE
    # --------------------------------------------------------

    if action_name == "write_file":

        return write_file(
            root,
            str(
                action.get(
                    "path",
                    "",
                )
            ),
            str(
                action.get(
                    "content",
                    "",
                )
            ),
        )

    # --------------------------------------------------------
    # DELETE
    # --------------------------------------------------------

    if action_name == "delete_file":

        return delete_file(
            root,
            str(
                action.get(
                    "path",
                    "",
                )
            ),
        )

    # --------------------------------------------------------
    # GIT STATUS
    # --------------------------------------------------------

    if action_name == "git_status":

        return run_process(
            [
                "git",
                "status",
                "--short",
            ],
            root,
        )

    # --------------------------------------------------------
    # GIT DIFF
    # --------------------------------------------------------

    if action_name == "git_diff":

        return {
            "summary": diff_summary(
                root
            ),
            "diff": full_git_diff(
                root
            ),
        }

    # --------------------------------------------------------
    # TEST
    # --------------------------------------------------------

    if action_name == "run_test":

        commands = (
            session.project.get(
                "test_commands",
                [],
            )
        )

        if not commands:

            return {
                "skipped": True,
                "success": True,
                "reason": (
                    "No supported test command detected."
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

        result = results[-1]

        session.last_test = result

        return {
            "type": "test",
            "results": results,
            **result,
        }

    # --------------------------------------------------------
    # BUILD
    # --------------------------------------------------------

    if action_name == "run_build":

        commands = (
            session.project.get(
                "build_commands",
                [],
            )
        )

        if not commands:

            return {
                "skipped": True,
                "success": True,
                "reason": (
                    "No supported build command detected."
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
            "type": "build",
            "results": results,
            **results[-1],
        }

    # --------------------------------------------------------
    # TYPECHECK
    # --------------------------------------------------------

    if action_name == "typecheck":

        commands = (
            session.project.get(
                "typecheck_commands",
                [],
            )
        )

        if not commands:

            return {
                "skipped": True,
                "success": True,
                "reason": (
                    "No supported typecheck command detected."
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
            "type": "typecheck",
            "results": results,
            **results[-1],
        }

    # --------------------------------------------------------
    # COMMIT
    # --------------------------------------------------------

    if action_name == "git_commit":

        message = str(
            action.get(
                "message",
                "",
            )
        ).strip()

        if len(message) < 5:

            raise ValueError(
                "Commit message must be at least 5 characters."
            )

        add_result = run_process(
            [
                "git",
                "add",
                "-A",
            ],
            root,
        )

        if not add_result["success"]:

            return {
                "success": False,
                "stage": add_result,
            }

        commit_result = run_process(
            [
                "git",
                "commit",
                "-m",
                message,
            ],
            root,
        )

        sha = None

        if commit_result["success"]:

            sha_result = run_process(
                [
                    "git",
                    "rev-parse",
                    "HEAD",
                ],
                root,
            )

            sha = (
                sha_result["stdout"].strip()
            )

        return {
            "success": commit_result["success"],
            "message": message,
            "commit": commit_result,
            "sha": sha,
        }

    # --------------------------------------------------------
    # PUSH
    # --------------------------------------------------------

    if action_name == "git_push":

        if not os.getenv(
            "GITHUB_TOKEN"
        ):

            raise ValueError(
                "GITHUB_TOKEN is not configured."
            )

        branch = (
            session.repository.get(
                "branch"
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

        if not branch:

            raise ValueError(
                "Could not determine current Git branch."
            )

        result = run_process(
            [
                "git",
                "push",
                "origin",
                branch,
            ],
            root,
        )

        return {
            "success": result["success"],
            "branch": branch,
            "result": result,
        }

    # --------------------------------------------------------
    # FINISH
    # --------------------------------------------------------

    if action_name == "finish":

        return {
            "finished": True,
            "success": True,
        }

    raise ValueError(
        "Unhandled action."
    )


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "Advanced ChatGPT-like software engineering agent."
    ),
)


origins = [
    x.strip()
    for x in os.getenv(
        "FRONTEND_ORIGINS",
        "*",
    ).split(",")
    if x.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# BASIC ROUTES
# ============================================================

@app.get("/")
def home():

    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "docs": "/docs",
        "api": {
            "chat": "/chat",
            "plan": "/plan",
            "work": "/work/execute",
            "commit": "/work/commit",
            "push": "/work/push",
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
            "auto_testing": True,
            "error_fix_loop": True,
            "git_diff": True,
            "commit": True,
            "push": True,
            "zip": True,
            "json_requests": True,
            "form_requests": True,
        },
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
async def chat(
    request: Request,
):

    data = await read_request_data(
        request
    )

    message = required_string(
        data,
        "message",
    )

    context = data.get(
        "conversation_context",
        "",
    )

    prompt = f"""
You are Open Agent.

You behave like a helpful ChatGPT-style AI assistant.

Rules:
- Reply naturally.
- Support all human languages.
- Detect the user's language automatically.
- Do not modify files in Chat Mode.
- Do not access GitHub in Chat Mode.
- Explain clearly.
- Help with coding, planning, debugging, writing,
  architecture, research and general questions.
- Never pretend an action was performed when it was not.

Conversation context:
{context_to_text(context)}

User:
{message}
"""

    reply = GEMINI.generate(
        prompt
    )

    return {
        "ok": True,
        "reply": reply,
    }


# ============================================================
# PLAN
# ============================================================

@app.post("/plan")
async def create_plan(
    request: Request,
):

    data = await read_request_data(
        request
    )

    task = required_string(
        data,
        "task",
    )

    repo_url = str(
        data.get(
            "repo_url",
            "",
        )
    )

    context = data.get(
        "conversation_context",
        "",
    )

    prompt = f"""
You are Open Agent in PLAN MODE.

Behave like ChatGPT plus a senior software architect.

The user is discussing a software task.

Do NOT modify files.
Do NOT commit.
Do NOT push.
Do NOT execute commands.

Analyze the task deeply.

Return a clear plan containing:

1. Goal
2. Understanding
3. Requirements
4. Architecture
5. Repository areas likely affected
6. Files likely to change
7. Implementation steps
8. Testing strategy
9. Error handling
10. Risks
11. Questions that actually require clarification

The user can continue discussing the plan.
Do not force Work Mode.

Task:
{task}

Repository:
{repo_url or "Not provided"}

Conversation:
{context_to_text(context)}
"""

    result = GEMINI.generate(
        prompt
    )

    return {
        "ok": True,
        "plan": result,
    }


# ============================================================
# FINALIZE PLAN
# ============================================================

@app.post("/plan/finalize")
async def finalize_plan(
    request: Request,
):

    data = await read_request_data(
        request
    )

    task = required_string(
        data,
        "task",
    )

    draft_plan = data.get(
        "draft_plan"
    )

    if draft_plan is None:

        raise api_error(
            "MISSING_FIELD",
            "draft_plan is required.",
            422,
        )

    prompt = f"""
You are preparing a FINAL WORK MODE specification.

Return ONLY valid JSON.

Schema:

{{
  "goal": "...",
  "requirements": [],
  "files": [],
  "changes": [],
  "tests": [],
  "risks": [],
  "steps": []
}}

Do not invent repository facts.

Task:
{task}

Draft plan:
{json.dumps(
    draft_plan,
    ensure_ascii=False,
)}

After this response, the specification will be used
to authorize Work Mode.
"""

    result = GEMINI.generate(
        prompt,
        json_mode=True,
    )

    return {
        "ok": True,
        "plan": result,
    }


# ============================================================
# REPOSITORY TEMPORARY CLONE
# ============================================================

def temporary_clone(
    repo_url: str,
) -> tuple[Path, dict[str, Any]]:

    session_id = (
        "read-"
        + uuid.uuid4().hex
    )

    workspace = new_workspace(
        session_id
    )

    repository = clone_repo(
        repo_url,
        workspace / "repo",
    )

    return workspace, repository


# ============================================================
# REPOSITORY INSPECT
# ============================================================

@app.post("/repository/inspect")
async def repository_inspect(
    request: Request,
):

    data = await read_request_data(
        request
    )

    repo_url = required_string(
        data,
        "repo_url",
    )

    workspace, repository = temporary_clone(
        repo_url
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
                for k, v in project.items()
                if k not in {
                    "files",
                    "test_commands",
                    "build_commands",
                    "typecheck_commands",
                }
            },
            "files": project["files"],
            "detected_commands": {
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


# ============================================================
# REPOSITORY READ
# ============================================================

@app.post("/repository/read")
async def repository_read(
    request: Request,
):

    data = await read_request_data(
        request
    )

    repo_url = required_string(
        data,
        "repo_url",
    )

    file_path = required_string(
        data,
        "file_path",
    )

    workspace, repository = temporary_clone(
        repo_url
    )

    try:

        content = read_file(
            workspace / "repo",
            file_path,
        )

        return {
            "ok": True,
            "repository": repository,
            "path": file_path,
            "content": content,
        }

    finally:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )


# ============================================================
# REPOSITORY SEARCH
# ============================================================

@app.post("/repository/search")
async def repository_search(
    request: Request,
):

    data = await read_request_data(
        request
    )

    repo_url = required_string(
        data,
        "repo_url",
    )

    query = required_string(
        data,
        "query",
    )

    workspace, repository = temporary_clone(
        repo_url
    )

    try:

        root = (
            workspace / "repo"
        )

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

            try:

                if (
                    path.stat().st_size
                    > MAX_FILE_SIZE
                ):
                    continue

                text = path.read_text(
                    errors="replace"
                )

                for line_number, line in enumerate(
                    text.splitlines(),
                    1,
                ):

                    if (
                        query.lower()
                        in line.lower()
                    ):

                        matches.append(
                            {
                                "path": relative,
                                "line": line_number,
                                "text": line[:1000],
                            }
                        )

                        if len(matches) >= 300:
                            break

            except OSError:
                continue

            if len(matches) >= 300:
                break

        return {
            "ok": True,
            "repository": repository,
            "query": query,
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
async def work_prepare(
    request: Request,
):

    data = await read_request_data(
        request
    )

    session_id = required_string(
        data,
        "session_id",
    )

    repo_url = required_string(
        data,
        "repo_url",
    )

    task = required_string(
        data,
        "task",
    )

    approved_plan = data.get(
        "approved_plan"
    )

    if approved_plan is None:

        raise api_error(
            "PLAN_NOT_APPROVED",
            "approved_plan is required before Work Mode.",
            400,
        )

    workspace = new_workspace(
        session_id
    )

    session = Session(
        id=session_id,
        mode="work",
        workspace=workspace,
        task=task,
        approved_plan=approved_plan,
    )

    SESSIONS[
        session_id
    ] = session

    try:

        repository = clone_repo(
            repo_url,
            workspace / "repo",
        )

        session.repository = repository

        root = (
            workspace / "repo"
        )

        branch_name = (
            f"open-agent/{session_id}"
        )

        checkout = run_process(
            [
                "git",
                "checkout",
                "-b",
                branch_name,
            ],
            root,
        )

        if not checkout["success"]:

            raise api_error(
                "BRANCH_CREATION_FAILED",
                checkout["stderr"],
                500,
            )

        session.repository[
            "branch"
        ] = branch_name

        session.project = detect_project(
            root
        )

        session.status = "prepared"

        session.log(
            "info",
            "workspace",
            "Work Mode prepared.",
            branch=branch_name,
        )

        return {
            "ok": True,
            "session_id": session_id,
            "status": session.status,
            "repository": session.repository,
            "project": {
                k: v
                for k, v in session.project.items()
                if k not in {
                    "files",
                    "test_commands",
                    "build_commands",
                    "typecheck_commands",
                }
            },
            "files": session.project[
                "files"
            ],
            "detected_commands": {
                "test": session.project[
                    "test_commands"
                ],
                "build": session.project[
                    "build_commands"
                ],
                "typecheck": session.project[
                    "typecheck_commands"
                ],
            },
        }

    except Exception:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )

        SESSIONS.pop(
            session_id,
            None,
        )

        raise


# ============================================================
# AGENT PROMPT
# ============================================================

def build_agent_prompt(
    session: Session,
) -> str:

    root = (
        session.workspace / "repo"
    )

    current_diff = diff_summary(
        root
    )

    last_test = (
        session.last_test
        or {}
    )

    recent_iterations = (
        session.iterations[-5:]
    )

    return f"""
You are Open Agent, an autonomous senior software
engineering agent operating in WORK MODE.

You have explicit user authorization to modify the
repository for the approved task.

IMPORTANT:
- Work only inside the repository workspace.
- Do not use shell commands directly.
- Use the structured actions below.
- Inspect the repository before making assumptions.
- You may modify multiple files.
- You may create directories.
- Preserve existing architecture unless the task requires changes.
- Do not expose secrets.
- Never read sensitive credential files.
- Never claim success without verification.
- After code changes, run appropriate tests/build/typecheck.
- If a test fails, diagnose the failure and fix it.
- Repeat the test -> diagnose -> fix cycle when necessary.
- Continue until the task is actually complete.
- Finish only after verification or when safe progress is impossible.

TASK:
{session.task}

APPROVED PLAN:
{json.dumps(
    session.approved_plan,
    ensure_ascii=False,
)}

PROJECT:
{json.dumps(
    {
        k: v
        for k, v in session.project.items()
        if k != "files"
    },
    ensure_ascii=False,
)}

CURRENT FILE TREE:
{json.dumps(
    session.project.get(
        "files",
        []
    )[:2000],
    ensure_ascii=False,
)}

CURRENT GIT STATE:
{json.dumps(
    current_diff,
    ensure_ascii=False,
)}

LAST TEST RESULT:
{json.dumps(
    last_test,
    ensure_ascii=False,
)}

RECENT ITERATIONS:
{json.dumps(
    recent_iterations,
    ensure_ascii=False,
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
10. typecheck
11. git_commit
12. git_push
13. finish

ACTION FORMAT:

For reading:
{{
  "action": "read_file",
  "path": "path/to/file"
}}

For searching:
{{
  "action": "search_files",
  "query": "text"
}}

For writing:
{{
  "action": "write_file",
  "path": "path/to/file",
  "content": "COMPLETE FILE CONTENT"
}}

For deleting:
{{
  "action": "delete_file",
  "path": "path/to/file"
}}

For testing:
{{
  "action": "run_test"
}}

For building:
{{
  "action": "run_build"
}}

For typechecking:
{{
  "action": "typecheck"
}}

For commit:
{{
  "action": "git_commit",
  "message": "meaningful commit message"
}}

For push:
{{
  "action": "git_push"
}}

For completion:
{{
  "action": "finish"
}}

Return ONLY ONE valid JSON action.

Prefer:
inspect -> understand -> edit -> test -> diagnose -> fix -> retest -> verify -> finish.

Do not make random changes.
"""


# ============================================================
# WORK EXECUTION
# ============================================================

@app.post("/work/execute")
async def work_execute(
    request: Request,
):

    data = await read_request_data(
        request
    )

    session_id = required_string(
        data,
        "session_id",
    )

    task = required_string(
        data,
        "task",
    )

    approved_plan = data.get(
        "approved_plan"
    )

    session = get_session(
        session_id
    )

    if session.mode != "work":

        raise api_error(
            "INVALID_MODE",
            "Session is not a Work Mode session.",
        )

    if task != session.task:

        raise api_error(
            "AUTHORIZATION_MISMATCH",
            "Task does not match the authorized Work Mode session.",
            403,
        )

    if (
        json.dumps(
            approved_plan,
            sort_keys=True,
            ensure_ascii=False,
        )
        !=
        json.dumps(
            session.approved_plan,
            sort_keys=True,
            ensure_ascii=False,
        )
    ):

        raise api_error(
            "AUTHORIZATION_MISMATCH",
            "Approved plan does not match the authorized plan.",
            403,
        )

    if session.status not in {
        "prepared",
        "paused",
        "partial",
    }:

        raise api_error(
            "INVALID_SESSION_STATE",
            f"Cannot start Work Mode from status: {session.status}",
        )

    session.status = "running"
    session.cancelled = False

    session.log(
        "info",
        "work",
        "Work Mode started.",
    )

    root = (
        session.workspace / "repo"
    )

    completed = False
    last_action = None

    try:

        for iteration in range(
            1,
            MAX_AGENT_ITERATIONS + 1,
        ):

            if session.cancelled:

                session.status = "stopped"

                return {
                    "ok": False,
                    "status": "stopped",
                    "message": "Work cancelled.",
                    "iterations": session.iterations,
                }

            prompt = build_agent_prompt(
                session
            )

            action = GEMINI.generate(
                prompt,
                json_mode=True,
            )

            if not isinstance(
                action,
                dict,
            ):

                raise ValueError(
                    "AI returned an invalid action object."
                )

            last_action = action

            started = time.monotonic()

            try:

                result = execute_action(
                    session,
                    action,
                )

                action_error = None

            except HTTPException as exc:

                result = {
                    "success": False,
                    "error": exc.detail,
                }

                action_error = str(
                    exc.detail
                )

            except Exception as exc:

                result = {
                    "success": False,
                    "error": redact(
                        str(exc)
                    ),
                }

                action_error = redact(
                    str(exc)
                )

            record = {
                "iteration": iteration,
                "action": action,
                "result": result,
                "error": action_error,
                "files_changed": diff_summary(
                    root
                ),
                "duration_ms": int(
                    (
                        time.monotonic()
                        - started
                    ) * 1000
                ),
            }

            session.iterations.append(
                record
            )

            if action.get(
                "action"
            ) in {
                "run_test",
                "run_build",
                "typecheck",
            }:

                session.last_test = result

            if action.get(
                "action"
            ) == "finish":

                completed = True
                break

        if completed:

            session.status = "completed"

        else:

            session.status = "partial"

        return {
            "ok": completed,
            "status": session.status,
            "summary": (
                "Work completed and verified."
                if completed
                else
                "Maximum agent iterations reached."
            ),
            "last_action": last_action,
            "files_changed": diff_summary(
                root
            ),
            "git_diff": full_git_diff(
                root
            ),
            "tests": [
                x["result"]
                for x in session.iterations
                if x["action"].get(
                    "action"
                ) in {
                    "run_test",
                    "run_build",
                    "typecheck",
                }
            ],
            "iterations": session.iterations,
        }

    except HTTPException:

        session.status = "failed"
        raise

    except Exception as exc:

        session.status = "failed"

        session.log(
            "error",
            "work",
            "Work execution failed.",
            error=redact(
                str(exc)
            ),
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
# EXPLICIT COMMIT ENDPOINT
# /work/commit
# ============================================================

@app.post("/work/commit")
async def work_commit(
    request: Request,
):

    data = await read_request_data(
        request
    )

    session_id = required_string(
        data,
        "session_id",
    )

    message = required_string(
        data,
        "message",
    )

    session = get_session(
        session_id
    )

    if session.mode != "work":

        raise api_error(
            "INVALID_MODE",
            "Commit requires Work Mode.",
        )

    if session.status not in {
        "prepared",
        "running",
        "completed",
        "partial",
        "paused",
    }:

        raise api_error(
            "INVALID_SESSION_STATE",
            "Session is not available for commit.",
        )

    result = execute_action(
        session,
        {
            "action": "git_commit",
            "message": message,
        },
    )

    session.log(
        "info",
        "git",
        "Commit operation completed.",
        message=message,
    )

    return {
        "ok": result.get(
            "success",
            False,
        ),
        "operation": "commit",
        "session_id": session_id,
        "result": result,
        "git": diff_summary(
            session.workspace / "repo"
        ),
    }


# ============================================================
# EXPLICIT PUSH ENDPOINT
# /work/push
# ============================================================

@app.post("/work/push")
async def work_push(
    request: Request,
):

    data = await read_request_data(
        request
    )

    session_id = required_string(
        data,
        "session_id",
    )

    session = get_session(
        session_id
    )

    if session.mode != "work":

        raise api_error(
            "INVALID_MODE",
            "Push requires Work Mode.",
        )

    if not os.getenv(
        "GITHUB_TOKEN"
    ):

        raise api_error(
            "GITHUB_NOT_CONFIGURED",
            "GITHUB_TOKEN is not configured on the server.",
            503,
        )

    result = execute_action(
        session,
        {
            "action": "git_push",
        },
    )

    session.log(
        "info",
        "git",
        "Push operation completed.",
        branch=result.get(
            "branch"
        ),
    )

    return {
        "ok": result.get(
            "success",
            False,
        ),
        "operation": "push",
        "session_id": session_id,
        "result": result,
    }


# ============================================================
# MANUAL REPOSITORY EDIT
# ============================================================

@app.post("/repository/edit")
async def repository_edit(
    request: Request,
):

    data = await read_request_data(
        request
    )

    session_id = required_string(
        data,
        "session_id",
    )

    file_path = required_string(
        data,
        "file_path",
    )

    content = str(
        data.get(
            "content",
            "",
        )
    )

    commit_message = str(
        data.get(
            "commit_message",
            "",
        )
    ).strip()

    session = get_session(
        session_id
    )

    if session.mode != "work":

        raise api_error(
            "INVALID_MODE",
            "Work Mode session required.",
        )

    edit_result = write_file(
        session.workspace / "repo",
        file_path,
        content,
    )

    diff = diff_summary(
        session.workspace / "repo"
    )

    commit_result = None

    if commit_message:

        commit_result = execute_action(
            session,
            {
                "action": "git_commit",
                "message": commit_message,
            },
        )

    return {
        "ok": True,
        "edit": edit_result,
        "diff": diff,
        "commit": commit_result,
    }


# ============================================================
# STOP
# ============================================================

@app.post("/work/stop")
async def work_stop(
    request: Request,
):

    data = await read_request_data(
        request
    )

    session_id = required_string(
        data,
        "session_id",
    )

    session = get_session(
        session_id
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
        "session_id": session_id,
        "status": "stopped",
    }


# ============================================================
# STATUS
# ============================================================

@app.get("/work/status/{session_id}")
def work_status(
    session_id: str,
):

    session = get_session(
        session_id
    )

    return {
        "ok": True,
        "session_id": session.id,
        "mode": session.mode,
        "status": session.status,
        "cancelled": session.cancelled,
        "repository": session.repository,
        "project": {
            k: v
            for k, v in session.project.items()
            if k not in {
                "files",
                "test_commands",
                "build_commands",
                "typecheck_commands",
            }
        },
        "iteration_count": len(
            session.iterations
        ),
        "git": diff_summary(
            session.workspace / "repo"
        ),
    }


# ============================================================
# LOGS
# ============================================================

@app.get("/work/logs/{session_id}")
def work_logs(
    session_id: str,
):

    session = get_session(
        session_id
    )

    return {
        "ok": True,
        "session_id": session_id,
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

    if not file.filename:

        raise api_error(
            "INVALID_FILE",
            "ZIP file is required.",
        )

    if not file.filename.lower().endswith(
        ".zip"
    ):

        raise api_error(
            "INVALID_FILE",
            "Only ZIP files are supported.",
        )

    archive = await file.read()

    if len(archive) > ARCHIVE_MAX_SIZE:

        raise api_error(
            "ARCHIVE_TOO_LARGE",
            "ZIP archive is too large.",
        )

    workspace = new_workspace(
        session_id
    )

    session = Session(
        id=session_id,
        mode="zip",
        workspace=workspace,
    )

    SESSIONS[
        session_id
    ] = session

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

            for entry in archive_file.infolist():

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
                        f"ZIP entry too large: {entry.filename}",
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

        session.project = detect_project(
            root
        )

        session.status = "uploaded"

        return {
            "ok": True,
            "session_id": session_id,
            "status": session.status,
            "files": session.project[
                "files"
            ],
            "project": {
                k: v
                for k, v in session.project.items()
                if k not in {
                    "files",
                    "test_commands",
                    "build_commands",
                    "typecheck_commands",
                }
            },
        }

    except zipfile.BadZipFile:

        raise api_error(
            "INVALID_ZIP",
            "Invalid ZIP archive.",
        )


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
            "Project workspace unavailable.",
            404,
        )

    archive = (
        session.workspace
        / "open-agent-result.zip"
    )

    with zipfile.ZipFile(
        archive,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zip_file:

        for relative in list_tree(
            root
        ):

            path = safe_path(
                root,
                relative,
            )

            if (
                path.is_file()
                and not is_sensitive(path)
            ):

                zip_file.write(
                    path,
                    relative,
                )

    return FileResponse(
        archive,
        filename=(
            f"open-agent-{session_id}.zip"
        ),
        media_type="application/zip",
    )


# ============================================================
# STARTUP CLEANUP
# ============================================================

@app.on_event("startup")
async def startup_cleanup():

    cutoff = (
        time.time()
        - 60 * 60 * 6
    )

    try:

        for path in BASE_DIR.iterdir():

            try:

                if (
                    path.is_dir()
                    and path.stat().st_mtime
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
# RUN
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
    )
