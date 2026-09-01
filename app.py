import os
import time
import random
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from google import genai


# =========================================================
# CONFIG
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is not configured")

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

MAX_RETRIES = 3

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)


# =========================================================
# GEMINI CLIENT
# =========================================================

client = None

if GEMINI_API_KEY:
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="Open Agent API",
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
# GEMINI RETRY SYSTEM
# =========================================================

def is_retryable_error(error: Exception) -> bool:
    error_text = str(error).lower()

    retryable_keywords = [
        "503",
        "429",
        "unavailable",
        "high demand",
        "resource exhausted",
        "temporarily unavailable",
        "service unavailable",
    ]

    return any(
        keyword in error_text
        for keyword in retryable_keywords
    )


def generate_with_retry(prompt: str) -> str:
    """
    Generate Gemini response with retry support
    for temporary errors such as 503 and 429.
    """

    if client is None:
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

            raise RuntimeError(
                "The AI model returned an empty response"
            )

        except Exception as error:

            last_error = error

            print(
                f"Gemini error "
                f"(attempt {attempt + 1}/{MAX_RETRIES}): "
                f"{error}"
            )

            if not is_retryable_error(error):
                raise

            if attempt < MAX_RETRIES - 1:

                # Exponential backoff
                # Attempt 1 -> ~2 seconds
                # Attempt 2 -> ~4 seconds
                delay = (
                    2 ** (attempt + 1)
                    + random.uniform(0, 1)
                )

                print(
                    f"Retrying in {delay:.1f} seconds..."
                )

                time.sleep(delay)

    raise RuntimeError(
        "The AI model is temporarily busy. "
        "Please try again in a moment."
    ) from last_error


# =========================================================
# HEALTH
# =========================================================

@app.get("/")
def root():
    return {
        "name": "Open Agent API",
        "status": "online",
        "model": MODEL_NAME
    }


@app.get("/health")
def health():

    return {
        "status": "ok",
        "model": MODEL_NAME,
        "gemini_configured": bool(GEMINI_API_KEY),
        "capabilities": {
            "chat": True,
            "plan_mode": True,
            "work_mode": True,
            "zip": True,
            "github": True,
            "streaming": False
        }
    }


# =========================================================
# NORMAL CHAT
# =========================================================

@app.post("/chat")
def chat(
    message: str = Form(...),
    conversation_context: Optional[str] = Form(None)
):
    """
    Normal ChatGPT-like conversation endpoint.
    """

    if not message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    prompt = f"""
You are Open Agent, a helpful AI assistant and
software engineering assistant.

You can communicate naturally in the user's language.

Reply in the same language used by the user whenever
possible.

Current conversation context:

{conversation_context or "No previous context."}

User message:

{message}

Answer naturally and helpfully.
"""

    try:

        answer = generate_with_retry(prompt)

        return {
            "ok": True,
            "reply": answer
        }

    except Exception as error:

        error_text = str(error)

        if is_retryable_error(error) or \
           "temporarily busy" in error_text.lower():

            raise HTTPException(
                status_code=503,
                detail=(
                    "The AI model is temporarily busy. "
                    "Please try again in a moment."
                )
            )

        raise HTTPException(
            status_code=500,
            detail=error_text
        )


# =========================================================
# PLAN MODE
# =========================================================

@app.post("/plan")
def create_plan(
    task: str = Form(...),
    conversation_context: Optional[str] = Form(None),
    repo_url: Optional[str] = Form(None),
    project_zip: Optional[UploadFile] = File(None)
):
    """
    Creates a planning response.
    This endpoint does not intentionally modify files.
    """

    if not task.strip():
        raise HTTPException(
            status_code=400,
            detail="Task cannot be empty"
        )

    project_info = ""

    if repo_url:
        project_info += (
            f"\nGitHub repository:\n{repo_url}\n"
        )

    if project_zip:
        project_info += (
            f"\nProject ZIP provided:\n"
            f"{project_zip.filename}\n"
        )

    prompt = f"""
You are Open Agent.

You are currently in PLAN MODE.

Important rules:

- Discuss naturally with the user.
- Do not claim to have modified files.
- Do not claim to have executed commands.
- Analyze requirements carefully.
- Ask questions when clarification is useful.
- Respect previous conversation decisions.
- Use the user's language.

Conversation context:

{conversation_context or "No previous conversation."}

Project information:

{project_info or "No project source provided."}

Current user request:

{task}

Provide a helpful planning response.
"""

    try:

        answer = generate_with_retry(prompt)

        return {
            "ok": True,
            "mode": "plan",
            "result": {
                "status": "completed",
                "steps": 1,
                "logs": [],
                "final": answer
            }
        }

    except Exception as error:

        error_text = str(error)

        if is_retryable_error(error):

            raise HTTPException(
                status_code=503,
                detail=(
                    "The AI model is temporarily busy. "
                    "Please try again shortly."
                )
            )

        raise HTTPException(
            status_code=500,
            detail=error_text
        )


# =========================================================
# MAIN /run ENDPOINT
# =========================================================

@app.post("/run")
async def run_agent(
    task: str = Form(...),
    mode: str = Form("work"),
    repo_url: Optional[str] = Form(None),
    approved_plan: Optional[str] = Form(None),
    conversation_context: Optional[str] = Form(None),
    project_zip: Optional[UploadFile] = File(None)
):
    """
    Main compatibility endpoint.

    Supports:
    - task
    - mode
    - repo_url
    - project_zip
    - approved_plan
    - conversation_context
    """

    if not task.strip():
        raise HTTPException(
            status_code=400,
            detail="Task cannot be empty"
        )

    mode = mode.lower().strip()

    if mode not in ["plan", "work", "chat"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid mode"
        )

    # -----------------------------------------------------
    # CHAT MODE
    # -----------------------------------------------------

    if mode == "chat":

        prompt = f"""
You are Open Agent, a conversational AI assistant.

Conversation context:

{conversation_context or "None"}

User:

{task}

Reply naturally in the user's language.
"""

        try:

            answer = generate_with_retry(prompt)

            return {
                "ok": True,
                "mode": "chat",
                "result": {
                    "status": "completed",
                    "steps": 1,
                    "logs": [],
                    "final": answer
                }
            }

        except Exception as error:

            raise HTTPException(
                status_code=503
                if is_retryable_error(error)
                else 500,
                detail=(
                    "The AI model is temporarily busy. "
                    "Please try again."
                    if is_retryable_error(error)
                    else str(error)
                )
            )

    # -----------------------------------------------------
    # PLAN MODE
    # -----------------------------------------------------

    if mode == "plan":

        prompt = f"""
You are Open Agent in PLAN MODE.

Do not pretend that you modified files.

Analyze the user's request and conversation.

Conversation:

{conversation_context or "None"}

Repository:

{repo_url or "None"}

Task:

{task}

Provide a detailed but practical implementation plan.
"""

        try:

            answer = generate_with_retry(prompt)

            return {
                "ok": True,
                "mode": "plan",
                "result": {
                    "status": "completed",
                    "steps": 1,
                    "logs": [],
                    "final": answer
                }
            }

        except Exception as error:

            raise HTTPException(
                status_code=503
                if is_retryable_error(error)
                else 500,
                detail=(
                    "The AI model is temporarily busy. "
                    "Please try again."
                    if is_retryable_error(error)
                    else str(error)
                )
            )

    # -----------------------------------------------------
    # WORK MODE
    # -----------------------------------------------------

    workspace = None

    try:

        workspace = Path(
            tempfile.mkdtemp(
                prefix="open_agent_"
            )
        )

        logs = []

        logs.append(
            "Agent workspace prepared"
        )

        # -------------------------------------------------
        # ZIP PROJECT
        # -------------------------------------------------

        if project_zip:

            if not project_zip.filename.lower().endswith(
                ".zip"
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Project must be a ZIP file"
                )

            zip_path = workspace / "project.zip"

            with open(zip_path, "wb") as file:

                shutil.copyfileobj(
                    project_zip.file,
                    file
                )

            logs.append(
                f"Project ZIP received: "
                f"{project_zip.filename}"
            )

            try:

                with zipfile.ZipFile(
                    zip_path,
                    "r"
                ) as archive:

                    archive.extractall(
                        workspace / "project"
                    )

                logs.append(
                    "Project ZIP extracted"
                )

            except zipfile.BadZipFile:

                raise HTTPException(
                    status_code=400,
                    detail="Invalid ZIP file"
                )

        # -------------------------------------------------
        # REPOSITORY
        # -------------------------------------------------

        if repo_url:

            logs.append(
                f"Repository requested: {repo_url}"
            )

        # -------------------------------------------------
        # AGENT PROMPT
        # -------------------------------------------------

        prompt = f"""
You are Open Agent in WORK MODE.

The user has explicitly allowed the agent to work.

Your task:

{task}

Approved plan:

{approved_plan or "No separate approved plan was provided."}

Conversation context:

{conversation_context or "No conversation context provided."}

Repository:

{repo_url or "No repository provided."}

Important:

Be honest about what you actually did.

Do not claim to have modified files unless a real file
operation was performed by the backend.

Do not claim tests passed unless they were actually run.

Provide a useful final report.

Reply in the user's language where possible.
"""

        logs.append(
            "Requesting AI analysis"
        )

        answer = generate_with_retry(prompt)

        logs.append(
            "AI response completed"
        )

        # -------------------------------------------------
        # CURRENT VERSION NOTE
        # -------------------------------------------------

        logs.append(
            "Work response completed"
        )

        return {
            "ok": True,
            "mode": "work",
            "result": {
                "status": "completed",
                "steps": len(logs),
                "logs": logs,
                "final": answer
            },
            "download_url": None
        }

    except HTTPException:
        raise

    except Exception as error:

        print(f"Agent error: {error}")

        status_code = (
            503
            if is_retryable_error(error)
            else 500
        )

        raise HTTPException(
            status_code=status_code,
            detail=(
                "The AI model is temporarily busy. "
                "Please try again in a moment."
                if status_code == 503
                else str(error)
            )
        )

    finally:

        # Workspace cleanup.
        # Keep this disabled if you later need to package
        # modified project files into a ZIP.
        if workspace and workspace.exists():
            shutil.rmtree(
                workspace,
                ignore_errors=True
            )


# =========================================================
# DOWNLOAD
# =========================================================

@app.get("/download/{filename}")
def download_file(filename: str):

    safe_filename = Path(filename).name

    file_path = (
        DOWNLOAD_DIR /
        safe_filename
    )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/zip"
    )


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup_event():

    print("=================================")
    print("Open Agent API started")
    print(f"Model: {MODEL_NAME}")
    print(
        f"Gemini configured: "
        f"{bool(GEMINI_API_KEY)}"
    )
    print("=================================")
