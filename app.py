import os
import subprocess
import tempfile
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI()

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Mini SWE Agent</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 700px;
            margin: auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .box {
            background: white;
            padding: 20px;
            border-radius: 14px;
            box-shadow: 0 2px 10px #ddd;
        }
        input, textarea, button {
            width: 100%;
            box-sizing: border-box;
            margin-top: 10px;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #ccc;
        }
        textarea {
            height: 150px;
        }
        button {
            background: #111;
            color: white;
            border: none;
            cursor: pointer;
        }
        pre {
            white-space: pre-wrap;
            background: #111;
            color: #eee;
            padding: 15px;
            border-radius: 10px;
            overflow-x: auto;
        }
    </style>
</head>
<body>
<div class="box">
    <h2>🤖 Mini SWE Agent</h2>

    <form method="post">
        <label>GitHub Repository URL</label>
        <input
            name="repo"
            placeholder="https://github.com/user/project"
            required
        >

        <label>Task</label>
        <textarea
            name="task"
            placeholder="Fix the mobile responsive problems..."
            required
        ></textarea>

        <button type="submit">🚀 Run Agent</button>
    </form>

    {result}
</div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(HTML.format(result=""))

@app.post("/", response_class=HTMLResponse)
def run_agent(repo: str = Form(...), task: str = Form(...)):

    token = os.getenv("GITHUB_TOKEN")

    if not token:
        return HTMLResponse(
            HTML.format(
                result="<p>❌ GITHUB_TOKEN is not configured.</p>"
            )
        )

    workdir = tempfile.mkdtemp()

    if repo.startswith("https://github.com/"):
        clone_url = repo.replace(
            "https://github.com/",
            f"https://x-access-token:{token}@github.com/"
        )
    else:
        return HTMLResponse(
            HTML.format(
                result="<p>❌ Invalid GitHub repository URL.</p>"
            )
        )

    try:
        subprocess.run(
            ["git", "clone", clone_url, workdir],
            check=True,
            capture_output=True,
            text=True
        )

        result = subprocess.run(
            [
                "mini",
                "--model",
                os.getenv("MODEL", ""),
                task
            ],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=900
        )

        output = result.stdout + "\n" + result.stderr

        return HTMLResponse(
            HTML.format(
                result=f"<h3>Agent Output</h3><pre>{output}</pre>"
            )
        )

    except Exception as e:
        return HTMLResponse(
            HTML.format(
                result=f"<h3>❌ Error</h3><pre>{e}</pre>"
            )
        )
