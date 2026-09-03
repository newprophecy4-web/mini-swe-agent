import io
import zipfile

from fastapi.testclient import TestClient

import app as open_agent


client = TestClient(open_agent.app)


def test_health_exposes_runtime_limits_without_secrets():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["limits"]["max_upload_size"] == open_agent.MAX_UPLOAD_SIZE
    assert "GEMINI_API_KEY" not in response.text
    assert "GITHUB_TOKEN" not in response.text


def test_work_prepare_requires_explicit_authorization():
    response = client.post("/work/prepare", json={"authorization": False})
    assert response.status_code == 403


def test_safe_path_rejects_workspace_escape():
    session = open_agent.create_session("test")
    session.workspace = open_agent.WORKSPACE_ROOT / session.id
    session.workspace.mkdir(parents=True, exist_ok=True)
    try:
        response = client.post(
            "/repository/read",
            json={"session_id": session.id, "path": "../../etc/passwd"},
        )
        assert response.status_code == 400
        assert "escapes workspace" in response.text
    finally:
        open_agent.SESSIONS.pop(session.id, None)


def test_zip_upload_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(open_agent, "WORKSPACE_ROOT", tmp_path / "workspace")
    monkeypatch.setattr(open_agent, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(open_agent, "EXPORT_ROOT", tmp_path / "exports")
    for path in (open_agent.WORKSPACE_ROOT, open_agent.UPLOAD_ROOT, open_agent.EXPORT_ROOT):
        path.mkdir(parents=True, exist_ok=True)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../escape.txt", "blocked")
    archive.seek(0)

    response = client.post(
        "/project/upload",
        files={"file": ("unsafe.zip", archive.getvalue(), "application/zip")},
    )
    assert response.status_code == 400
    assert "Unsafe ZIP path" in response.text
