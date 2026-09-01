import os
import subprocess
import tempfile
from html import escape

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI()


def page(result=""):
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mini SWE Agent</title>

<style>
body {{
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f3f4f6;
}}

.container {{
    max-width: 700px;
    margin: auto;
    padding: 20px;
}}

.card {{
    background: white;
    padding: 20px;
    border-radius: 16px;
    box-shadow: 0 4px 20px rgba(0,0,0,.08);
}}

h1 {{
    margin-top: 0;
}}

input, textarea, button {{
    width: 100%;
    box-sizing: border-box;
    margin-top: 10px;
    padding: 13px;
    border-radius: 10px;
    border: 1px solid #ddd;
    font-size: 16px;
}}

textarea {{
    min-height: 150px;
    resize: vertical;
}}

button {{
    background: #111;
    color: white;
    border: none;
    font-weight: bold;
}}

pre {{
    margin-top: 20px;
    background: #111;
    color: #eee;
    padding: 15px;
    border-radius: 10px;
    white-space: pre-wrap;
    overflow-x: auto;
}}
</style>
</head>

<body>
<div class="container">
<div class="card">

<h1>🤖 Mini SWE Agent</h1>

<form method="post">

<label>Public GitHub Repository</label>

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
</div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return page()


@app.post("/", response_class=HTMLResponse)
def run_agent(
    repo: str = Form(...),
    task: str = Form(...)
):

    if not repo.startswith("https://github.com/"):
        return page(
            "<pre>❌ Please enter a valid public GitHub repository URL.</pre>"
        )

    workdir = tempfile.mkdtemp()

    try:

        # Clone public repository
        clone = subprocess.run(
            ["git", "clone", repo, workdir],
            capture_output=True,
            text=True,
            timeout=120
        )

        if clone.returncode != 0:
            return page(
                f"<pre>{escape(clone.stderr)}</pre>"
            )

        # Run mini-SWE-agent
        command = [
            "mini",
            "--model",
            "gemini/gemini-2.5-flash",
            task
        ]

        result = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=900
        )

        output = result.stdout + "\n" + result.stderr

        return page(
            f"<h3>Agent Output</h3><pre>{escape(output)}</pre>"
        )

    except subprocess.TimeoutExpired:
        return page(
            "<pre>⏱️ Agent timed out.</pre>"
        )

    except Exception as e:
        return page(
            f"<pre>❌ {escape(str(e))}</pre>"
        )
