import os
import time
import random
import shutil
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from google import genai


# =========================================================
# CONFIG
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

MAX_RETRIES = 3

client = None

if GEMINI_API_KEY:
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Open Agent API",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# GEMINI
# =========================================================

def is_retryable_error(error):
    text = str(error).lower()

    return any(x in text for x in [
        "503",
        "429",
        "unavailable",
        "high demand",
        "resource exhausted",
        "service unavailable",
    ])


def generate_with_retry(prompt):
    if not client:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured"
        )

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )

            text = getattr(response, "text", None)

            if text and text.strip():
                return text.strip()

            raise RuntimeError("Empty AI response")

        except Exception as error:
            last_error = error

            if not is_retryable_error(error):
                raise

            if attempt < MAX_RETRIES - 1:
                delay = (
                    2 ** (attempt + 1)
                    + random.uniform(0, 1)
                )

                time.sleep(delay)

    raise RuntimeError(
        "AI model is temporarily busy. "
        "Please try again later."
    ) from last_error


# =========================================================
# GITHUB URL
# =========================================================

def validate_github_url(repo_url):
    parsed = urlparse(repo_url)

    if parsed.netloc not in [
        "github.com",
        "www.github.com"
    ]:
        raise HTTPException(
            status_code=400,
            detail="Only GitHub repositories are supported"
        )

    path = parsed.path.strip("/")

    if path.endswith(".git"):
        path = path[:-4]

    parts = path.split("/")

    if len(parts) < 2:
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub repository URL"
        )

    owner = parts[0]
    repo = parts[1]

    return owner, repo


def authenticated_repo_url(repo_url):
    owner, repo = validate_github_url(repo_url)

    if GITHUB_TOKEN:
        return (
            f"https://x-access-token:"
            f"{GITHUB_TOKEN}"
            f"@github.com/{owner}/{repo}.git"
        )

    return (
        f"https://github.com/"
        f"{owner}/{repo}.git"
    )


# =========================================================
# GIT COMMAND
# =========================================================

def run_command(command, cwd=None):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr or result.stdout
            )

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Command timed out"
        )


# =========================================================
# CLONE REPOSITORY
# =========================================================

def clone_repository(repo_url):
    workspace = Path(
        tempfile.mkdtemp(
            prefix="open_agent_repo_"
        )
    )

    repo_dir = workspace / "repository"

    clone_url = authenticated_repo_url(
        repo_url
    )

    try:
        run_command([
            "git",
            "clone",
            "--depth",
            "1",
            clone_url,
            str(repo_dir)
        ])

        return workspace, repo_dir

    except Exception:
        shutil.rmtree(
            workspace,
            ignore_errors=True
        )
        raise


# =========================================================
# SAFE PATH
# =========================================================

def safe_file_path(repo_dir, relative_path):
    relative_path = relative_path.lstrip("/")

    target = (
        repo_dir /
        relative_path
    ).resolve()

    repo_root = repo_dir.resolve()

    if target != repo_root and \
       repo_root not in target.parents:

        raise HTTPException(
            status_code=400,
            detail="Invalid file path"
        )

    return target


# =========================================================
# FILE TREE
# =========================================================

def get_file_tree(repo_dir):
    files = []

    ignored = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
    }

    for path in repo_dir.rglob("*"):

        if any(
            part in ignored
            for part in path.parts
        ):
            continue

        if path.is_file():

            relative = path.relative_to(
                repo_dir
            )

            files.append(
                str(relative)
            )

    return sorted(files)


# =========================================================
# PROJECT CONTEXT
# =========================================================

def build_project_context(
    repo_dir,
    max_files=30,
    max_chars_per_file=6000
):
    tree = get_file_tree(repo_dir)

    important_extensions = [
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".html",
        ".css",
        ".json",
        ".md",
        ".yaml",
        ".yml",
    ]

    selected = []

    for relative in tree:
        if len(selected) >= max_files:
            break

        path = repo_dir / relative

        if path.suffix.lower() in \
           important_extensions:

            selected.append(relative)

    context = []

    context.append(
        "PROJECT FILE TREE:\n" +
        "\n".join(tree[:300])
    )

    for relative in selected:

        path = repo_dir / relative

        try:
            content = path.read_text(
                encoding="utf-8",
                errors="ignore"
            )

            content = content[
                :max_chars_per_file
            ]

            context.append(
                f"\n\nFILE: {relative}\n"
                f"```\n{content}\n```"
            )

        except Exception:
            continue

    return "\n".join(context)


# =========================================================
# HEALTH
# =========================================================

@app.get("/")
def root():
    return {
        "name": "Open Agent API",
        "status": "online"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "gemini_configured": bool(
            GEMINI_API_KEY
        ),
        "github_configured": bool(
            GITHUB_TOKEN
        ),
        "capabilities": {
            "chat": True,
            "github_read": True,
            "github_edit": True,
            "github_commit": True,
            "github_push": True
        }
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(
    message: str = Form(...),
    conversation_context: str = Form("")
):
    if not message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    prompt = f"""
You are Open Agent.

Reply naturally and helpfully.

Use the same language as the user when possible.

Conversation context:

{conversation_context}

User message:

{message}
"""

    try:
        answer = generate_with_retry(
            prompt
        )

        return {
            "ok": True,
            "reply": answer
        }

    except Exception as error:
        raise HTTPException(
            status_code=503
            if is_retryable_error(error)
            else 500,
            detail=str(error)
        )


# =========================================================
# INSPECT REPOSITORY
# =========================================================

@app.post("/repository/inspect")
def inspect_repository(
    repo_url: str = Form(...)
):
    workspace = None

    try:
        workspace, repo_dir = \
            clone_repository(repo_url)

        owner, repo = validate_github_url(
            repo_url
        )

        tree = get_file_tree(repo_dir)

        return {
            "ok": True,
            "accessible": True,
            "repository": {
                "owner": owner,
                "name": repo
            },
            "file_count": len(tree),
            "files": tree[:500]
        }

    except Exception as error:
        return {
            "ok": False,
            "accessible": False,
            "error": str(error)
        }

    finally:
        if workspace:
            shutil.rmtree(
                workspace,
                ignore_errors=True
            )


# =========================================================
# READ FILE
# =========================================================

@app.post("/repository/read")
def read_repository_file(
    repo_url: str = Form(...),
    file_path: str = Form(...)
):
    workspace = None

    try:
        workspace, repo_dir = \
            clone_repository(repo_url)

        target = safe_file_path(
            repo_dir,
            file_path
        )

        if not target.exists():
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )

        if not target.is_file():
            raise HTTPException(
                status_code=400,
                detail="Not a file"
            )

        content = target.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        return {
            "ok": True,
            "path": file_path,
            "content": content
        }

    finally:
        if workspace:
            shutil.rmtree(
                workspace,
                ignore_errors=True
            )


# =========================================================
# EDIT FILE + COMMIT + PUSH
# =========================================================

@app.post("/repository/edit")
def edit_repository_file(
    repo_url: str = Form(...),
    file_path: str = Form(...),
    content: str = Form(...),
    commit_message: str = Form(
        "Update file via Open Agent"
    )
):
    workspace = None

    try:
        workspace, repo_dir = \
            clone_repository(repo_url)

        target = safe_file_path(
            repo_dir,
            file_path
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        target.write_text(
            content,
            encoding="utf-8"
        )

        run_command([
            "git",
            "config",
            "user.name",
            "Open Agent"
        ], cwd=repo_dir)

        run_command([
            "git",
            "config",
            "user.email",
            "open-agent@localhost"
        ], cwd=repo_dir)

        run_command([
            "git",
            "add",
            file_path
        ], cwd=repo_dir)

        run_command([
            "git",
            "commit",
            "-m",
            commit_message
        ], cwd=repo_dir)

        commit_hash = run_command([
            "git",
            "rev-parse",
            "HEAD"
        ], cwd=repo_dir)

        run_command([
            "git",
            "push",
            "origin",
            "HEAD"
        ], cwd=repo_dir)

        return {
            "ok": True,
            "message": "File updated and pushed",
            "file": file_path,
            "commit": commit_hash
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:
        if workspace:
            shutil.rmtree(
                workspace,
                ignore_errors=True
            )


# =========================================================
# WORK MODE
# =========================================================

@app.post("/work")
def work(
    repo_url: str = Form(...),
    task: str = Form(...),
    approved_plan: str = Form("")
):
    workspace = None

    try:
        workspace, repo_dir = \
            clone_repository(repo_url)

        project_context = \
            build_project_context(
                repo_dir
            )

        prompt = f"""
You are Open Agent in WORK MODE.

You have successfully accessed the target
GitHub repository.

User task:

{task}

Approved plan:

{approved_plan}

Repository context:

{project_context}

Analyze the project and explain precisely:

1. Which files should change.
2. What changes are needed.
3. Any risks or conflicts.
4. A concrete implementation approach.

Do not claim that files were changed unless
the backend actually performed an edit operation.
"""

        answer = generate_with_retry(
            prompt
        )

        return {
            "ok": True,
            "mode": "work",
            "repository_access": True,
            "analysis": answer
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:
        if workspace:
            shutil.rmtree(
                workspace,
                ignore_errors=True
            )
