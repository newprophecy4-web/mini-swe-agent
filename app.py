import os
import re
import json
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from google import genai
from google.genai import types


# =========================================================
# CONFIG
# =========================================================

APP_NAME = "Open Agent"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

MAX_UPLOAD_MB = int(
    os.getenv("MAX_UPLOAD_MB", "50")
)

MAX_COMMAND_SECONDS = int(
    os.getenv("MAX_COMMAND_SECONDS", "20")
)

MAX_AGENT_STEPS = int(
    os.getenv("MAX_AGENT_STEPS", "12")
)

BASE_DIR = Path(
    tempfile.gettempdir()
) / "open-agent"

BASE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title=APP_NAME,
    version="1.0.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# HEALTH
# =========================================================

@app.get("/")
def root():
    return {
        "name": APP_NAME,
        "status": "online",
        "model": GEMINI_MODEL,
        "gemini_configured": bool(
            GEMINI_API_KEY
        )
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": GEMINI_MODEL,
        "gemini_configured": bool(
            GEMINI_API_KEY
        )
    }


# =========================================================
# WORKSPACE
# =========================================================

def create_workspace():
    return Path(
        tempfile.mkdtemp(
            prefix="agent_",
            dir=BASE_DIR
        )
    )


def safe_path(
    workspace: Path,
    user_path: str
):

    user_path = (
        user_path
        .strip()
        .replace("\\", "/")
    )

    if user_path.startswith("/"):
        raise ValueError(
            "Absolute paths are not allowed."
        )

    target = (
        workspace / user_path
    ).resolve()

    root = workspace.resolve()

    if (
        target != root
        and root not in target.parents
    ):
        raise ValueError(
            "Path is outside workspace."
        )

    return target


# =========================================================
# FILE TOOLS
# =========================================================

def list_files(
    workspace: Path,
    path: str = "."
):

    target = safe_path(
        workspace,
        path
    )

    if not target.exists():
        return f"Path not found: {path}"

    results = []

    for item in sorted(
        target.rglob("*")
    ):

        if not item.exists():
            continue

        rel = item.relative_to(
            workspace
        )

        if any(
            part in {
                ".git",
                "node_modules",
                "__pycache__",
                ".venv",
                "venv",
                "dist",
                "build",
                ".next"
            }
            for part in rel.parts
        ):
            continue

        if item.is_dir():
            results.append(
                f"DIR  {rel}"
            )
        else:
            results.append(
                f"FILE {rel}"
            )

        if len(results) >= 500:
            results.append(
                "... listing truncated ..."
            )
            break

    return "\n".join(results)


def read_file(
    workspace: Path,
    path: str
):

    target = safe_path(
        workspace,
        path
    )

    if not target.exists():
        return f"File not found: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    if target.stat().st_size > 2_000_000:
        return "File is larger than 2 MB."

    try:
        return target.read_text(
            encoding="utf-8",
            errors="replace"
        )

    except Exception as exc:
        return f"Read error: {exc}"


def write_file(
    workspace: Path,
    path: str,
    content: str
):

    target = safe_path(
        workspace,
        path
    )

    if len(
        content.encode("utf-8")
    ) > 3_000_000:
        return "File is too large."

    target.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    target.write_text(
        content,
        encoding="utf-8"
    )

    return (
        f"Successfully wrote: {path}"
    )


def search_files(
    workspace: Path,
    pattern: str
):

    try:
        regex = re.compile(
            pattern,
            re.IGNORECASE
        )
    except Exception as exc:
        return f"Invalid regex: {exc}"

    results = []

    for file in workspace.rglob("*"):

        if not file.is_file():
            continue

        rel = file.relative_to(
            workspace
        )

        if any(
            part in {
                ".git",
                "node_modules",
                "__pycache__",
                ".venv",
                "venv"
            }
            for part in rel.parts
        ):
            continue

        try:
            if file.stat().st_size > 1_000_000:
                continue

            text = file.read_text(
                encoding="utf-8",
                errors="ignore"
            )

        except Exception:
            continue

        for line_no, line in enumerate(
            text.splitlines(),
            1
        ):

            if regex.search(line):

                results.append(
                    f"{rel}:{line_no}: "
                    f"{line[:300]}"
                )

                if len(results) >= 200:
                    return "\n".join(
                        results
                    )

    return (
        "\n".join(results)
        if results
        else "No matches found."
    )


# =========================================================
# TERMINAL
# =========================================================

def dangerous_command(
    command: str
):

    command = command.lower().strip()

    blocked = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "shutdown",
        "reboot",
        "poweroff",
        "init 0",
        "dd if=",
        "chmod 777 /",
        "chown -r",
        "mount ",
        "umount ",
        "iptables",
        "systemctl",
        "service ",
        "sudo ",
        "passwd",
        "useradd",
        "userdel",
        "curl | sh",
        "wget | sh",
        "curl | bash",
        "wget | bash",
        ":(){"
    ]

    return any(
        item in command
        for item in blocked
    )


def run_terminal(
    workspace: Path,
    command: str
):

    if not command.strip():
        return "Empty command."

    if len(command) > 2000:
        return "Command too long."

    if dangerous_command(
        command
    ):
        return (
            "Command blocked "
            "by security policy."
        )

    try:

        result = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=MAX_COMMAND_SECONDS,
            env={
                **os.environ,
                "HOME": str(workspace)
            }
        )

        output = result.stdout or ""

        if result.stderr:
            output += (
                "\n[stderr]\n"
                + result.stderr
            )

        output += (
            f"\n[exit code: "
            f"{result.returncode}]"
        )

        return output[-15000:]

    except subprocess.TimeoutExpired:
        return (
            f"Command timed out "
            f"after {MAX_COMMAND_SECONDS}s."
        )

    except Exception as exc:
        return f"Terminal error: {exc}"


# =========================================================
# WEB
# =========================================================

def web_fetch(url: str):

    if not url.startswith(
        ("http://", "https://")
    ):
        return (
            "Only HTTP/HTTPS URLs "
            "are allowed."
        )

    try:

        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent":
                "Open-Agent/1.0"
            }
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "content-type",
            ""
        )

        if "json" in content_type:
            return response.text[:20000]

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg"
        ]):
            tag.decompose()

        text = soup.get_text(
            "\n"
        )

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        return "\n".join(lines)[:20000]

    except Exception as exc:
        return (
            f"Web fetch failed: {exc}"
        )


def web_search(query: str):

    try:

        url = (
            "https://html.duckduckgo.com/"
            "html/?q="
            + quote_plus(query)
        )

        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent":
                "Mozilla/5.0"
            }
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        for item in soup.select(
            ".result"
        ):

            link = item.select_one(
                ".result__a"
            )

            if not link:
                continue

            snippet = item.select_one(
                ".result__snippet"
            )

            results.append({
                "title":
                    link.get_text(
                        " ",
                        strip=True
                    ),
                "url":
                    link.get("href", ""),
                "snippet":
                    snippet.get_text(
                        " ",
                        strip=True
                    )
                    if snippet
                    else ""
            })

            if len(results) >= 8:
                break

        return json.dumps(
            results,
            ensure_ascii=False
        )

    except Exception as exc:
        return (
            f"Search failed: {exc}"
        )


# =========================================================
# GITHUB PUBLIC REPOSITORY
# =========================================================

def clone_public_repo(
    workspace: Path,
    repo_url: str
):

    if not repo_url.startswith(
        "https://github.com/"
    ):
        raise ValueError(
            "Only public GitHub HTTPS "
            "repositories are supported."
        )

    result = subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            repo_url,
            str(workspace)
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr[-5000:]
        )

    return "GitHub repository cloned."


# =========================================================
# ZIP
# =========================================================

def extract_zip(
    zip_path: Path,
    workspace: Path
):

    with zipfile.ZipFile(
        zip_path
    ) as archive:

        root = workspace.resolve()

        for member in archive.infolist():

            target = (
                workspace
                / member.filename
            ).resolve()

            if (
                target != root
                and root not in target.parents
            ):
                raise ValueError(
                    "Unsafe ZIP path."
                )

        archive.extractall(
            workspace
        )


def create_zip(
    workspace: Path
):

    output = Path(
        tempfile.mktemp(
            suffix=".zip",
            dir=BASE_DIR
        )
    )

    with zipfile.ZipFile(
        output,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:

        for file in workspace.rglob("*"):

            if not file.is_file():
                continue

            if ".git" in file.parts:
                continue

            archive.write(
                file,
                file.relative_to(
                    workspace
                )
            )

    return output


# =========================================================
# GEMINI TOOLS
# =========================================================

FUNCTIONS = [

    types.FunctionDeclaration(
        name="list_files",
        description=(
            "List project files."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string"
                }
            }
        }
    ),

    types.FunctionDeclaration(
        name="read_file",
        description=(
            "Read a project text file."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string"
                }
            },
            "required": ["path"]
        }
    ),

    types.FunctionDeclaration(
        name="write_file",
        description=(
            "Create or replace a "
            "project text file."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string"
                },
                "content": {
                    "type": "string"
                }
            },
            "required": [
                "path",
                "content"
            ]
        }
    ),

    types.FunctionDeclaration(
        name="search_files",
        description=(
            "Search project files "
            "using regex."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string"
                }
            },
            "required": ["pattern"]
        }
    ),

    types.FunctionDeclaration(
        name="run_terminal",
        description=(
            "Run a terminal command "
            "inside the project."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string"
                }
            },
            "required": ["command"]
        }
    ),

    types.FunctionDeclaration(
        name="web_search",
        description=(
            "Search the public web."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string"
                }
            },
            "required": ["query"]
        }
    ),

    types.FunctionDeclaration(
        name="web_fetch",
        description=(
            "Fetch a public webpage "
            "and extract text."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string"
                }
            },
            "required": ["url"]
        }
    )
]


TOOLS = [
    types.Tool(
        function_declarations=FUNCTIONS
    )
]


SYSTEM_PROMPT = """
You are Open Agent, a general-purpose
AI software engineering agent.

You work inside a temporary project workspace.

For coding tasks:

1. Inspect the project first.
2. Identify relevant files.
3. Read the relevant files.
4. Make precise changes.
5. Run appropriate tests.
6. Inspect errors.
7. Fix problems when possible.
8. Do not modify unrelated files.
9. Never claim a change was made unless
   you actually made it.

Available capabilities:

- List files
- Read files
- Write files
- Search files
- Run terminal commands
- Search the public web
- Fetch public webpages

Security rules:

- Never expose secrets.
- Never request or reveal API keys.
- Do not perform destructive system operations.
- Stay inside the project workspace.
- Do not access private repositories.

When complete, provide a concise summary.
"""


# =========================================================
# AGENT
# =========================================================

def execute_tool(
    workspace: Path,
    name: str,
    args: dict
):

    if name == "list_files":
        return list_files(
            workspace,
            args.get("path", ".")
        )

    if name == "read_file":
        return read_file(
            workspace,
            args["path"]
        )

    if name == "write_file":
        return write_file(
            workspace,
            args["path"],
            args["content"]
        )

    if name == "search_files":
        return search_files(
            workspace,
            args["pattern"]
        )

    if name == "run_terminal":
        return run_terminal(
            workspace,
            args["command"]
        )

    if name == "web_search":
        return web_search(
            args["query"]
        )

    if name == "web_fetch":
        return web_fetch(
            args["url"]
        )

    return "Unknown tool."


def run_agent(
    workspace: Path,
    task: str
):

    if not client:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=task
                )
            ]
        )
    ]

    logs = []

    for step in range(
        1,
        MAX_AGENT_STEPS + 1
    ):

        logs.append(
            f"===== STEP {step} ====="
        )

        response = (
            client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=
                        SYSTEM_PROMPT,
                    tools=TOOLS,
                    temperature=0.2
                )
            )
        )

        if not response.candidates:
            break

        candidate = (
            response.candidates[0]
        )

        if candidate.content:
            contents.append(
                candidate.content
            )

        calls = (
            response.function_calls
            or []
        )

        if not calls:

            final_text = (
                response.text
                or "Task completed."
            )

            logs.append(
                final_text
            )

            return {
                "status": "completed",
                "steps": step,
                "logs": logs,
                "final": final_text
            }

        tool_parts = []

        for call in calls:

            name = call.name
            args = dict(
                call.args or {}
            )

            logs.append(
                f"TOOL: {name}"
            )

            result = execute_tool(
                workspace,
                name,
                args
            )

            logs.append(
                result[:5000]
            )

            tool_parts.append(
                types.Part.from_function_response(
                    name=name,
                    response={
                        "result": result
                    }
                )
            )

        contents.append(
            types.Content(
                role="tool",
                parts=tool_parts
            )
        )

    return {
        "status": "max_steps",
        "steps": MAX_AGENT_STEPS,
        "logs": logs,
        "final":
            "Maximum agent steps reached."
    }


# =========================================================
# RUN API
# =========================================================

@app.post("/run")
async def run_agent_api(
    task: str = Form(...),
    repo_url: str = Form(""),
    project_zip:
        UploadFile | None =
        File(None)
):

    if not task.strip():
        raise HTTPException(
            status_code=400,
            detail="Task is required."
        )

    workspace = create_workspace()

    try:

        # -----------------------------------------
        # ZIP
        # -----------------------------------------

        if (
            project_zip
            and project_zip.filename
        ):

            filename = Path(
                project_zip.filename
            ).name

            if not filename.lower().endswith(
                ".zip"
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Only ZIP files allowed."
                )

            data = await project_zip.read()

            if (
                len(data)
                > MAX_UPLOAD_MB
                * 1024
                * 1024
            ):
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"ZIP exceeds "
                        f"{MAX_UPLOAD_MB} MB."
                    )
                )

            zip_path = (
                workspace / filename
            )

            zip_path.write_bytes(
                data
            )

            extract_zip(
                zip_path,
                workspace
            )

            zip_path.unlink(
                missing_ok=True
            )

        # -----------------------------------------
        # PUBLIC GITHUB
        # -----------------------------------------

        elif repo_url.strip():

            clone_public_repo(
                workspace,
                repo_url.strip()
            )

        # -----------------------------------------
        # EMPTY PROJECT
        # -----------------------------------------

        else:

            (
                workspace
                / "README.md"
            ).write_text(
                "# Open Agent Workspace\n",
                encoding="utf-8"
            )

        # -----------------------------------------
        # AGENT
        # -----------------------------------------

        result = run_agent(
            workspace,
            task
        )

        # -----------------------------------------
        # ZIP
        # -----------------------------------------

        result_zip = create_zip(
            workspace
        )

        return JSONResponse({
            "ok": True,
            "result": result,
            "download_url":
                f"/download/"
                f"{result_zip.name}"
        })

    except HTTPException:
        raise

    except Exception as exc:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(exc)
            }
        )

    finally:

        # Keep generated ZIPs,
        # clean workspace separately.
        shutil.rmtree(
            workspace,
            ignore_errors=True
        )


# =========================================================
# DOWNLOAD
# =========================================================

@app.get("/download/{filename}")
def download_file(
    filename: str
):

    safe_name = Path(
        filename
    ).name

    file_path = (
        BASE_DIR / safe_name
    )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found."
        )

    return FileResponse(
        path=file_path,
        filename="open-agent-result.zip",
        media_type="application/zip"
    )
