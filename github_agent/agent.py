import os
import json
import subprocess
import re
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

# -------------------------
# Setup
# -------------------------

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
console = Console()

MAX_STEPS = 15

# -------------------------
# Safety guardrails
# -------------------------

BLOCKED_COMMANDS = [
    "rm -rf", "shutdown", "reboot", "mkfs", ":(){:|:&};:"
]

def is_safe_command(command: str):
    return not any(b in command for b in BLOCKED_COMMANDS)

# -------------------------
# Smart command approval
# -------------------------

AUTO_APPROVE = [
    "git add",
    "git commit",
    "git status",
    "git branch",
    "git checkout"
]

CONFIRM_REQUIRED = [
    "git push",
    "git push --force",
    "gh repo create"
]

def should_auto(cmd):
    return any(cmd.startswith(p) for p in AUTO_APPROVE)

def should_confirm(cmd):
    return any(p in cmd for p in CONFIRM_REQUIRED)

# -------------------------
# Commit message generator
# -------------------------

def generate_commit_message():
    diff = subprocess.run(
        "git diff --staged",
        shell=True,
        capture_output=True,
        text=True
    ).stdout[:3000]

    if not diff.strip():
        return "chore: update project files"

    prompt = f"""
    Generate a professional git commit message.

    Rules:
    - Use conventional commit style (feat, fix, refactor, chore)
    - Keep it concise and meaningful
    - 1 line summary only

    Diff:
    {diff}
    """
    client2 = OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1"
    )
    response = client2.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()

# -------------------------
# TOOLS
# -------------------------

def run_command(command: str):

    if not is_safe_command(command):
        return {"error": "Blocked unsafe command"}

    # ✅ Auto approve safe commands
    if not should_auto(command) and should_confirm(command):
        if not Confirm.ask(f"[yellow]Confirm:[/yellow] [bold]{command}[/bold]"):
            return {"error": "User skipped command"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )

        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }

    except Exception as e:
        return {"error": str(e)}

def create_repo(repo_name: str):
    return run_command(f"gh repo create {repo_name} --public --source=. --push")

TOOLS = {
    "run_command": {"fn": run_command},
    "create_repo": {"fn": create_repo}
}

# -------------------------
# SYSTEM PROMPT
# -------------------------

SYSTEM_PROMPT = """
You are a strict JSON-only GitHub automation agent.

You MUST ALWAYS respond in VALID JSON.

Do NOT write explanations.
Do NOT write text outside JSON.

Format:

{
 "step": "plan | action | observe | output",
 "content": "text",
 "function": "tool_name_if_action",
 "input": "command"
}

Rules:
- One JSON only
- No markdown
- Be precise

Tools:
run_command
create_repo
"""

messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# -------------------------
# JSON extractor (robust)
# -------------------------

def extract_json(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise Exception("Invalid JSON")

# -------------------------
# UI helpers
# -------------------------

def show_plan(text):
    console.print(Panel(f"[cyan]{text}[/cyan]", title="🧠 Plan"))

def show_action(cmd):
    console.print(f"[yellow]⚙️[/yellow] [bold]{cmd}[/bold]")

def show_success(msg="Done"):
    console.print(f"[green]✅ {msg}[/green]")

def show_error(msg):
    console.print(f"[red]❌ {msg}[/red]")

# -------------------------
# AGENT LOOP
# -------------------------

def run_agent(user_query):

    messages.append({"role": "user", "content": user_query})

    for _ in range(MAX_STEPS):

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )

        content = response.choices[0].message.content.strip()

        try:
            parsed = extract_json(content)
        except Exception:
            show_error("Invalid JSON from model")
            print(content)
            break

        messages.append({
            "role": "assistant",
            "content": json.dumps(parsed)
        })

        step_type = parsed.get("step")

        # -------------------------
        # PLAN
        # -------------------------
        if step_type == "plan":
            show_plan(parsed.get("content"))
            continue

        # -------------------------
        # ACTION
        # -------------------------
        if step_type == "action":

            tool_name = parsed.get("function")
            tool_input = parsed.get("input")

            # 🔥 Smart commit message injection
            if tool_input.startswith("git commit"):
                console.print("[cyan]🧠 Generating commit message...[/cyan]")
                msg = generate_commit_message()
                tool_input = f'git commit -m "{msg}"'

            show_action(tool_input)

            tool = TOOLS.get(tool_name)

            if not tool:
                observation = {"error": "Tool not found"}
                show_error("Tool not found")
            else:
                observation = tool["fn"](tool_input)

            # 🔁 Retry push if failed
            if observation.get("returncode") != 0 and "git push" in tool_input:
                console.print("[yellow]⚠️ Retrying push with upstream...[/yellow]")
                retry_cmd = "git push --set-upstream origin $(git branch --show-current)"
                observation = run_command(retry_cmd)

            if observation.get("returncode") == 0:
                show_success()
            elif observation.get("error"):
                show_error(observation.get("error"))
            else:
                show_error("Command failed")

            messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "step": "observe",
                    "output": observation
                })
            })

            continue

        # -------------------------
        # OUTPUT
        # -------------------------
        if step_type == "output":
            console.print(
                Panel(
                    f"[bold green]{parsed.get('content')}[/bold green]",
                    title="🎉 Result"
                )
            )
            break

# -------------------------
# CLI
# -------------------------

if __name__ == "__main__":

    console.print("[bold green]🚀 GitHub Agent Ready[/bold green]")

    while True:
        query = input("\n> ")

        if query.lower() == "exit":
            print("Bye 👋")
            break

        run_agent(query)