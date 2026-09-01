"""Open Agent backend: a guarded, mobile-compatible SWE agent API."""
from __future__ import annotations

import asyncio
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
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover
    genai = None
    types = None

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("open-agent")

BASE_DIR = Path(os.getenv("WORKSPACE_ROOT", "/tmp/open-agent")).resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "20"))
MAX_TEST_ITERATIONS = int(os.getenv("MAX_TEST_ITERATIONS", "5"))
WORKSPACE_TIMEOUT = int(os.getenv("WORKSPACE_TIMEOUT", "600"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "2000000"))
MAX_COMMAND_OUTPUT = int(os.getenv("MAX_COMMAND_OUTPUT", "120000"))
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "180"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AUTO_PUSH = os.getenv("AUTO_PUSH", "true").lower() == "true"

SENSITIVE_NAMES = {".env", ".env.local", ".env.production", "credentials", "id_rsa", "id_ed25519"}
SENSITIVE_PARTS = (".pem", ".key", "token", "secret", "password", "credential")
IGNORED_DIRS = {".git", "node_modules", "dist", "build", ".venv", "__pycache__", ".next"}
SAFE_COMMANDS: dict[str, list[list[str]]] = {
    "python": [["python", "-m", "pytest"], ["pytest"]],
    "node": [["npm", "test"]],
    "build": [["npm", "run", "build"]],
    "vite": [["npm", "run", "build"]],
    "next": [["npm", "run", "build"]],
    "typecheck": [["npm", "run", "typecheck"], ["npx", "tsc", "--noEmit"]],
    "go": [["go", "test", "./..."]],
    "rust": [["cargo", "test"]],
    "java": [["mvn", "test"]],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: str) -> str:
    for secret in (os.getenv("GITHUB_TOKEN"), os.getenv("GEMINI_API_KEY")):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def error(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"ok": False, "error": {"code": code, "message": message}})


def safe_path(root: Path, relative: str, *, allow_root: bool = False) -> Path:
    if not relative or "\x00" in relative:
        raise error("INVALID_FILE_PATH", "A non-empty relative path is required.")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise error("INVALID_FILE_PATH", "The path must remain inside the repository workspace.")
    if not allow_root and candidate == root.resolve():
        raise error("INVALID_FILE_PATH", "The repository root is not a file.")
    return candidate


def is_sensitive(path: str | Path) -> bool:
    parts = [p.lower() for p in Path(path).parts]
    name = parts[-1] if parts else ""
    return name in SENSITIVE_NAMES or any(any(marker in part for marker in SENSITIVE_PARTS) for part in parts)


def safe_content(path: str | Path, content: str) -> str:
    return "[REDACTED SENSITIVE FILE]" if is_sensitive(path) else content


def run_process(args: list[str], cwd: Path, timeout: int = COMMAND_TIMEOUT) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=os.environ.copy())
        stdout, stderr = proc.stdout[-MAX_COMMAND_OUTPUT:], proc.stderr[-MAX_COMMAND_OUTPUT:]
        return {"command": args, "stdout": redact(stdout), "stderr": redact(stderr), "exit_code": proc.returncode, "duration_ms": int((time.monotonic() - started) * 1000)}
    except subprocess.TimeoutExpired as exc:
        return {"command": args, "stdout": redact((exc.stdout or "")[-MAX_COMMAND_OUTPUT:]) if isinstance(exc.stdout, str) else "", "stderr": "Command timed out.", "exit_code": -1, "duration_ms": int((time.monotonic() - started) * 1000), "timed_out": True}
    except FileNotFoundError:
        return {"command": args, "stdout": "", "stderr": f"Required executable not found: {args[0]}", "exit_code": 127, "duration_ms": int((time.monotonic() - started) * 1000)}


def parse_github(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise error("INVALID_REQUEST", "Only github.com repository URLs are supported.")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[0]) or not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[1].removesuffix(".git")):
        raise error("INVALID_REQUEST", "Use a URL like https://github.com/owner/repository.git.")
    return parts[0], parts[1].removesuffix(".git")


def clone_repo(repo_url: str, destination: Path) -> dict[str, Any]:
    owner, name = parse_github(repo_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    token = env.get("GITHUB_TOKEN")
    # Credentials are passed through git's ephemeral HTTP header, never a URL or log.
    if token:
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
        env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: bearer {token}"
    try:
        proc = subprocess.run(["git", "clone", "--depth", "1", repo_url, str(destination)], capture_output=True, text=True, timeout=COMMAND_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        raise error("REPOSITORY_NOT_FOUND", "Repository clone timed out.", 504)
    if proc.returncode != 0:
        text = (proc.stderr or "").lower()
        if "authentication" in text or "private" in text or "403" in text:
            raise error("GITHUB_AUTH_REQUIRED", "The repository requires GitHub authentication.", 401)
        raise error("REPOSITORY_NOT_FOUND", "The repository could not be cloned.", 404)
    info = run_process(["git", "rev-parse", "HEAD"], destination)
    branch = run_process(["git", "branch", "--show-current"], destination)
    return {"owner": owner, "name": name, "branch": branch["stdout"].strip() or "HEAD", "commit": info["stdout"].strip()}


def list_tree(root: Path, limit: int = 1000) -> list[str]:
    output: list[str] = []
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        output.append(str(path.relative_to(root)))
        if len(output) >= limit:
            break
    return output


def detect_project(root: Path) -> dict[str, Any]:
    names = {p.name for p in root.iterdir()} if root.exists() else set()
    project_type, framework, package_manager = "unknown", None, None
    if "pyproject.toml" in names or "requirements.txt" in names or "setup.py" in names:
        project_type, package_manager = "python", "pip"
        test_commands = SAFE_COMMANDS["python"]
    elif "package.json" in names:
        project_type, package_manager = "node", "npm"
        try:
            package = json.loads((root / "package.json").read_text()[:MAX_FILE_SIZE])
            scripts = package.get("scripts", {})
            deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            framework = "Next.js" if "next" in deps or any("next.config" in n for n in names) else "Vite" if "vite" in deps or any(n.startswith("vite.config") for n in names) else "React" if "react" in deps else "Node.js"
            test_commands = [["npm", "test"]] if "test" in scripts else []
        except (OSError, json.JSONDecodeError):
            test_commands = []
    elif "go.mod" in names:
        project_type, package_manager, test_commands = "go", "go", SAFE_COMMANDS["go"]
    elif "Cargo.toml" in names:
        project_type, package_manager, test_commands = "rust", "cargo", SAFE_COMMANDS["rust"]
    elif "pom.xml" in names:
        project_type, package_manager, test_commands = "java", "maven", SAFE_COMMANDS["java"]
    else:
        test_commands = []
    build = SAFE_COMMANDS.get("next" if framework == "Next.js" else "vite" if framework == "Vite" else "build", []) if project_type == "node" else []
    return {"project_type": project_type, "framework": framework, "package_manager": package_manager, "test_commands": test_commands, "build_commands": build, "files": list_tree(root)}


def diff_summary(root: Path) -> dict[str, Any]:
    status = run_process(["git", "status", "--short"], root)
    diff = run_process(["git", "diff", "--stat"], root)
    added, modified, deleted = [], [], []
    for line in status["stdout"].splitlines():
        if len(line) >= 3:
            code, path = line[:2], line[3:]
            (deleted if "D" in code else added if "?" in code or "A" in code else modified).append(path)
    num = run_process(["git", "diff", "--numstat"], root)
    insertions = deletions = 0
    for line in num["stdout"].splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            insertions += int(fields[0]); deletions += int(fields[1])
    return {"files_added": added, "files_modified": modified, "files_deleted": deleted, "insertions": insertions, "deletions": deletions, "stat": diff["stdout"]}


@dataclass
class Session:
    id: str
    mode: str
    workspace: Path
    repository: dict[str, Any] = field(default_factory=dict)
    project: dict[str, Any] = field(default_factory=dict)
    approved_plan: dict[str, Any] = field(default_factory=dict)
    task: str = ""
    status: str = "prepared"
    cancelled: bool = False
    logs: list[dict[str, Any]] = field(default_factory=list)
    iterations: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, level: str, kind: str, message: str, **extra: Any) -> None:
        entry = {"timestamp": now(), "level": level, "type": kind, "message": redact(message), **extra}
        self.logs.append(entry)
        getattr(log, level if level in {"debug", "info", "warning", "error"} else "info")(redact(message))

SESSIONS: dict[str, Session] = {}


def new_workspace(session_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", session_id):
        raise error("INVALID_REQUEST", "session_id must contain 3-80 letters, numbers, underscores, or hyphens.")
    path = (BASE_DIR / session_id).resolve()
    try: path.relative_to(BASE_DIR)
    except ValueError: raise error("WORKSPACE_ERROR", "Invalid workspace.")
    if path.exists(): shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def get_session(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if not session:
        raise error("INVALID_REQUEST", "Unknown session_id.", 404)
    return session


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_context: str | list[dict[str, Any]] | None = None

class PlanRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20000)
    conversation_context: str | list[dict[str, Any]] | None = None
    repo_url: str | None = None

class FinalizeRequest(PlanRequest):
    draft_plan: Any

class RepoRequest(BaseModel):
    repo_url: str

class ReadRequest(RepoRequest):
    file_path: str

class SearchRequest(RepoRequest):
    query: str = Field(min_length=1, max_length=200)

class EditRequest(RepoRequest):
    session_id: str
    file_path: str
    content: str
    commit_message: str = Field(min_length=5, max_length=200)

class WorkRequest(BaseModel):
    session_id: str
    repo_url: str
    task: str
    approved_plan: dict[str, Any]

class StopRequest(BaseModel):
    session_id: str


class GeminiService:
    def __init__(self) -> None:
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) if genai and os.getenv("GEMINI_API_KEY") else None

    def text(self, prompt: str, *, json_mode: bool = False) -> Any:
        if not self.client:
            raise error("AI_TEMPORARILY_UNAVAILABLE", "Gemini is not configured on this server.", 503)
        config = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
        last = None
        for attempt in range(4):
            try:
                response = self.client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
                text = response.text or ""
                return json.loads(text) if json_mode else text
            except Exception as exc:  # provider SDK error classes vary by version
                last = exc
                marker = str(exc).lower()
                if not any(x in marker for x in ("429", "503", "unavailable", "resource exhausted", "temporarily")) or attempt == 3:
                    break
                time.sleep((2 ** attempt) + (0.1 * attempt))
        log.error("Gemini request failed after retries: %s", redact(str(last)))
        raise error("AI_TEMPORARILY_UNAVAILABLE", "The AI model is temporarily busy. Please try again.", 503)

GEMINI = GeminiService()


def context_text(context: Any) -> str:
    return json.dumps(context, ensure_ascii=False) if not isinstance(context, str) else context


def inspect_root(root: Path, repo: dict[str, Any]) -> dict[str, Any]:
    project = detect_project(root)
    return {"ok": True, "repository": repo, "project": {k: v for k, v in project.items() if k not in {"test_commands", "build_commands", "files"}}, "files": project["files"], "detected_commands": {"test": project["test_commands"], "build": project["build_commands"]}}

app = FastAPI(title="Open Agent Backend", version="1.0.0", description="A guarded AI software engineering agent backend.")
origins = [x.strip() for x in os.getenv("FRONTEND_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

@app.get("/", summary="Service information")
def root() -> dict[str, Any]:
    return {"name": "Open Agent Backend", "version": "1.0.0", "docs": "/docs"}

@app.get("/health", summary="Health and capability status")
def health() -> dict[str, Any]:
    configured = bool(os.getenv("GEMINI_API_KEY"))
    github = bool(os.getenv("GITHUB_TOKEN"))
    return {"status": "ok", "model": GEMINI_MODEL, "gemini_configured": configured, "github_configured": github, "capabilities": {"chat": configured, "plan_mode": configured, "github_read": True, "github_edit": True, "multi_file_edit": True, "auto_testing": True, "error_fix_loop": configured, "zip": True, "commit": True, "push": github}}

@app.post("/chat", summary="Chat without repository side effects")
def chat(request: ChatRequest) -> dict[str, Any]:
    prompt = f"You are Open Agent in chat-only mode. Do not call tools or modify repositories. Answer naturally and multilingual.\nContext:\n{context_text(request.conversation_context)}\nUser:\n{request.message}"
    return {"ok": True, "reply": GEMINI.text(prompt)}

@app.post("/plan", summary="Analyze requirements and propose a plan")
def plan(request: PlanRequest) -> dict[str, Any]:
    prompt = f"Produce a practical software implementation draft plan. Do not modify files. Include clarifying_questions, architecture, files, dependencies, tests, risks, steps.\nTask: {request.task}\nRepository: {request.repo_url or 'not provided'}\nContext: {context_text(request.conversation_context)}"
    return {"ok": True, "plan": GEMINI.text(prompt)}

@app.post("/plan/finalize", summary="Turn a draft into the Work Mode specification")
def finalize_plan(request: FinalizeRequest) -> dict[str, Any]:
    prompt = f"Return ONLY JSON with keys goal, requirements (array), files (array), changes (array), tests (array), risks (array), steps (array). Finalize this plan safely; do not invent repository facts.\nTask: {request.task}\nDraft: {json.dumps(request.draft_plan)}\nContext: {context_text(request.conversation_context)}"
    result = GEMINI.text(prompt, json_mode=True)
    plan_obj = {k: result.get(k, [] if k != "goal" else request.task) for k in ["goal", "requirements", "files", "changes", "tests", "risks", "steps"]}
    return {"ok": True, "plan": plan_obj}


def temporary_clone(repo_url: str) -> tuple[Path, dict[str, Any]]:
    sid = f"read-{uuid.uuid4().hex}"
    workspace = new_workspace(sid)
    repo = clone_repo(repo_url, workspace / "repo")
    return workspace, repo

@app.post("/repository/inspect", summary="Clone and inspect a GitHub repository")
def repository_inspect(request: RepoRequest) -> dict[str, Any]:
    workspace, repo = temporary_clone(request.repo_url)
    try: return inspect_root(workspace / "repo", repo)
    finally: shutil.rmtree(workspace, ignore_errors=True)

@app.post("/repository/read", summary="Read one non-sensitive repository file")
def repository_read(request: ReadRequest) -> dict[str, Any]:
    workspace, repo = temporary_clone(request.repo_url)
    try:
        path = safe_path(workspace / "repo", request.file_path)
        if is_sensitive(path.name): raise error("INVALID_REQUEST", "Sensitive files cannot be read.")
        if not path.is_file(): raise error("FILE_NOT_FOUND", "File not found.", 404)
        if path.stat().st_size > MAX_FILE_SIZE: raise error("INVALID_REQUEST", "File exceeds the configured size limit.")
        return {"ok": True, "path": request.file_path, "content": path.read_text(errors="replace"), "repository": repo}
    finally: shutil.rmtree(workspace, ignore_errors=True)

@app.post("/repository/search", summary="Search text inside a repository")
def repository_search(request: SearchRequest) -> dict[str, Any]:
    workspace, repo = temporary_clone(request.repo_url); matches = []
    try:
        for rel in list_tree(workspace / "repo"):
            path = safe_path(workspace / "repo", rel)
            if is_sensitive(path) or not path.is_file() or path.stat().st_size > MAX_FILE_SIZE: continue
            try:
                for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                    if request.query.lower() in line.lower(): matches.append({"path": rel, "line": number, "text": line[:500]})
            except OSError: continue
        return {"ok": True, "query": request.query, "matches": matches[:200], "repository": repo}
    finally: shutil.rmtree(workspace, ignore_errors=True)

@app.post("/project/upload", summary="Upload and safely extract a ZIP project")
async def project_upload(file: UploadFile = File(...), session_id: str = Form(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".zip"): raise error("INVALID_REQUEST", "Only ZIP uploads are supported.")
    session = Session(session_id, "zip", new_workspace(session_id)); SESSIONS[session_id] = session
    archive = await file.read()
    if len(archive) > 100 * MAX_FILE_SIZE: raise error("INVALID_REQUEST", "Archive is too large.")
    root = session.workspace / "repo"; root.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            for entry in zf.infolist():
                target = safe_path(root, entry.filename, allow_root=True)
                if entry.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
                if entry.file_size > MAX_FILE_SIZE: raise error("INVALID_REQUEST", "ZIP entry exceeds file size limit.")
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(zf.read(entry))
    except zipfile.BadZipFile: raise error("INVALID_REQUEST", "Invalid ZIP archive.")
    session.project = detect_project(root); session.status = "uploaded"; session.log("info", "project", "ZIP project uploaded", file_count=len(session.project["files"]))
    return inspect_root(root, {"source": "zip", "session_id": session_id})

@app.get("/project/download/{session_id}", summary="Download a sanitized ZIP project")
def project_download(session_id: str) -> FileResponse:
    session = get_session(session_id); root = session.workspace / "repo"
    if not root.exists(): raise error("FILE_NOT_FOUND", "Project workspace is unavailable.", 404)
    archive = session.workspace / "project-result.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in list_tree(root):
            path = safe_path(root, rel)
            if path.is_file() and not is_sensitive(path): zf.write(path, rel)
    return FileResponse(archive, filename=f"open-agent-{session_id}.zip", media_type="application/zip")

@app.post("/work/prepare", summary="Clone or initialize an explicitly requested work session")
def work_prepare(request: WorkRequest) -> dict[str, Any]:
    workspace = new_workspace(request.session_id); session = Session(request.session_id, "work", workspace, task=request.task, approved_plan=request.approved_plan); SESSIONS[request.session_id] = session
    if request.repo_url.startswith("zip:"):
        raise error("INVALID_REQUEST", "Use /project/upload before preparing a ZIP session.")
    repo = clone_repo(request.repo_url, workspace / "repo"); session.repository = repo
    branch = f"open-agent/{request.session_id}"; checkout = run_process(["git", "checkout", "-b", branch], workspace / "repo")
    if checkout["exit_code"] != 0: raise error("WORKSPACE_ERROR", "Could not create the isolated agent branch.")
    session.repository["branch"] = branch; session.project = detect_project(workspace / "repo"); session.status = "prepared"; session.log("info", "workspace", "Repository cloned and isolated branch created", branch=branch, commit=repo["commit"])
    return {"ok": True, "repository": session.repository, "project": {k:v for k,v in session.project.items() if k not in {"files", "test_commands", "build_commands"}}, "files": session.project["files"], "detected_commands": {"test": session.project["test_commands"], "build": session.project["build_commands"]}, "implementation_plan": request.approved_plan}


def validate_action(action: dict[str, Any]) -> str:
    allowed = {"list_files", "read_file", "search_files", "write_file", "delete_file", "git_status", "git_diff", "run_test", "run_build", "git_commit", "git_push", "finish"}
    name = action.get("action")
    if name not in allowed: raise ValueError(f"Unsupported action: {name}")
    return name


def execute_action(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    root = session.workspace / "repo"; name = validate_action(action); session.log("info", "tool", f"Executing {name}", action=name, path=action.get("path"))
    if name == "list_files": return {"files": list_tree(root)}
    if name == "read_file":
        path = safe_path(root, action.get("path", ""));
        if is_sensitive(path): raise ValueError("Sensitive files cannot be read")
        if not path.is_file(): raise ValueError("File not found")
        if path.stat().st_size > MAX_FILE_SIZE: raise ValueError("File exceeds size limit")
        return {"path": action["path"], "content": path.read_text(errors="replace")}
    if name == "search_files":
        query = str(action.get("query", "")); found=[]
        for rel in list_tree(root):
            path=safe_path(root, rel)
            if path.is_file() and not is_sensitive(path) and path.stat().st_size <= MAX_FILE_SIZE:
                for n,line in enumerate(path.read_text(errors="replace").splitlines(),1):
                    if query.lower() in line.lower(): found.append({"path":rel,"line":n,"text":line[:500]})
        return {"matches": found[:200]}
    if name == "write_file":
        content = action.get("content", "")
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE_SIZE: raise ValueError("Invalid or oversized file content")
        path = safe_path(root, action.get("path", "")); path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".open-agent-", dir=path.parent); os.close(fd)
        try: Path(tmp).write_text(content); os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return {"written": action["path"], "bytes": len(content.encode())}
    if name == "delete_file":
        path = safe_path(root, action.get("path", "")); rel = str(path.relative_to(root))
        if path.name == ".git" or is_sensitive(path) or any(p in {".git", ".env"} for p in Path(rel).parts): raise ValueError("Protected file cannot be deleted")
        if not path.is_file(): raise ValueError("File not found")
        path.unlink(); return {"deleted": rel}
    if name == "git_status": return run_process(["git", "status", "--short"], root)
    if name == "git_diff": return {"summary": diff_summary(root), "diff": run_process(["git", "diff", "--", "."], root)["stdout"][-MAX_COMMAND_OUTPUT:]}
    if name in {"run_test", "run_build"}:
        commands = session.project["test_commands"] if name == "run_test" else session.project["build_commands"]
        if not commands: return {"skipped": True, "reason": "No supported command detected."}
        for command in commands:
            result = run_process(command, root)
            if result["exit_code"] == 0 or len(commands) == 1: return result
        return result
    if name == "git_commit":
        message = str(action.get("message", ""))
        if len(message) < 5 or message.lower() in {"update", "changes", "test", "fix"}: raise ValueError("Commit message must be meaningful")
        add = run_process(["git", "add", "-A"], root); commit = run_process(["git", "commit", "-m", message], root)
        return {"add": add, "commit": commit, "sha": run_process(["git", "rev-parse", "HEAD"], root)["stdout"].strip() if commit["exit_code"] == 0 else None}
    if name == "git_push":
        if not AUTO_PUSH: return {"pushed": False, "reason": "AUTO_PUSH is disabled."}
        result = run_process(["git", "push", "origin", session.repository["branch"]], root); return {"pushed": result["exit_code"] == 0, "branch": session.repository["branch"], "result": result}
    return {"finished": True}

@app.post("/work/execute", summary="Run the guarded multi-file agent loop")
def work_execute(request: WorkRequest) -> dict[str, Any]:
    session = get_session(request.session_id)
    if session.status not in {"prepared", "uploaded"} or session.repository and session.repository.get("branch", "").startswith("open-agent/") is False and session.mode == "work":
        pass
    if request.approved_plan != session.approved_plan or request.task != session.task: raise error("INVALID_REQUEST", "Work authorization does not match the prepared session.")
    session.status = "running"; session.log("info", "work", "Work Mode started")
    root = session.workspace / "repo"; last_test = None; commit = {}; push = {}
    try:
        for iteration in range(1, MAX_AGENT_ITERATIONS + 1):
            if session.cancelled: session.status = "stopped"; raise error("WORK_CANCELLED", "Work was cancelled.")
            prompt = f"You are a software engineering agent. Return ONLY one JSON object describing the next structured action. Allowed actions: list_files, read_file, search_files, write_file, delete_file, git_status, git_diff, run_test, run_build, git_commit, git_push, finish. Task: {session.task}. Approved plan: {json.dumps(session.approved_plan)}. Project: {json.dumps(session.project)}. Recent test: {json.dumps(last_test)}. Recent diff: {json.dumps(diff_summary(root))}. Do not use shell commands. Prefer inspect/read before editing. After edits run tests/build. Finish only when requirements are met and tests pass, or no safe fix is possible. For write_file include path and complete content; for commit include message."
            action = GEMINI.text(prompt, json_mode=True); result = execute_action(session, action)
            record = {"iteration": iteration, "actions": [action], "files_changed": diff_summary(root), "test": result if action.get("action") in {"run_test", "run_build"} else {}, "error": None}
            if action.get("action") in {"run_test", "run_build"}: last_test = result
            if action.get("action") == "git_commit": commit = result
            if action.get("action") == "git_push": push = result
            session.iterations.append(record)
            if action.get("action") == "finish": break
        else: session.status = "partial"
        if session.status == "running": session.status = "completed"
        return {"ok": session.status == "completed", "status": session.status, "summary": "Agent execution completed." if session.status == "completed" else "Maximum agent iterations reached.", "files_changed": diff_summary(root), "tests": [x["test"] for x in session.iterations if x["test"]], "iterations": session.iterations, "commit": commit, "push": push, "errors": []}
    except HTTPException: raise
    except Exception as exc:
        session.status = "failed"; session.log("error", "work", "Work failed", error=redact(str(exc)))
        return {"ok": False, "status": "failed", "summary": "Execution stopped safely after an internal error.", "files_changed": diff_summary(root), "tests": [x["test"] for x in session.iterations if x["test"]], "iterations": session.iterations, "commit": commit, "push": push, "errors": [redact(str(exc))]}

@app.post("/repository/edit", summary="Edit, test, commit and optionally push in an authorized session")
def repository_edit(request: EditRequest) -> dict[str, Any]:
    session = get_session(request.session_id)
    if session.mode != "work" or session.status not in {"prepared", "uploaded"}: raise error("INVALID_REQUEST", "An explicitly authorized Work Mode session is required.")
    result = execute_action(session, {"action":"write_file", "path":request.file_path, "content":request.content})
    diff = diff_summary(session.workspace / "repo"); commit = execute_action(session, {"action":"git_commit", "message":request.commit_message})
    push = execute_action(session, {"action":"git_push"})
    return {"ok": True, "edit": result, "diff": diff, "commit": commit, "push": push}

@app.post("/work/stop", summary="Cancel a running work session")
def work_stop(request: StopRequest) -> dict[str, Any]:
    session = get_session(request.session_id); session.cancelled = True; session.status = "stopped"; session.log("warning", "work", "Cancellation requested"); return {"ok": True, "status": "stopped"}

@app.get("/work/status/{session_id}", summary="Get work session status")
def work_status(session_id: str) -> dict[str, Any]:
    session = get_session(session_id); return {"ok": True, "session_id": session.id, "mode": session.mode, "status": session.status, "repository": session.repository, "cancelled": session.cancelled, "iteration_count": len(session.iterations)}

@app.get("/work/logs/{session_id}", summary="Get structured work logs")
def work_logs(session_id: str) -> dict[str, Any]:
    session = get_session(session_id); return {"ok": True, "session_id": session.id, "logs": session.logs, "iterations": session.iterations}

@app.on_event("startup")
async def startup_cleanup() -> None:
    # Best-effort cleanup from prior process instances, without touching active sessions.
    cutoff = time.time() - WORKSPACE_TIMEOUT
    for path in BASE_DIR.iterdir():
        try:
            if path.is_dir() and path.stat().st_mtime < cutoff: shutil.rmtree(path, ignore_errors=True)
        except OSError: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
