import os
import json
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich import print

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
# TOOLS
# -------------------------

def run_command(command: str):

    if not is_safe_command(command):
        return {"error": "Blocked unsafe command"}

    # 🔒 Ask user before executing
    if not Confirm.ask(f"[yellow]Run command?[/yellow] [bold]{command}[/bold]"):
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

# -------------------------
# TOOL REGISTRY
# -------------------------

TOOLS = {
    "run_command": {"fn": run_command},
    "create_repo": {"fn": create_repo}
}

# -------------------------
# SYSTEM PROMPT
# -------------------------

SYSTEM_PROMPT = """
You are a GitHub automation agent who is specialize in all the github related operations.

You MUST ALWAYS respond in VALID JSON.

Do NOT write explanations.
Do NOT write text outside JSON.
Do NOT include markdown or code blocks.

You operate using these steps:

PLAN
ACTION
OBSERVE
OUTPUT

Allowed format:

{
 "step": "plan | action | observe | output",
 "content": "text",
 "function": "tool_name_if_action",
 "input": "command"
}

Rules:
- Only ONE JSON object per response
- No extra text before or after JSON
- No markdown (no ```json)
- If you fail format, system will break

You are controlling a real terminal. Be precise.

Available tools:

run_command
create_repo
"""

messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# -------------------------
# Helper UI functions
# -------------------------

def show_plan(text):
    console.print(Panel(f"[cyan]{text}[/cyan]", title="🧠 Plan"))

def show_action(cmd):
    console.print(f"[yellow]⚙️ Running:[/yellow] [bold]{cmd}[/bold]")

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
            parsed = json.loads(content)
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

            show_action(tool_input)

            tool = TOOLS.get(tool_name)

            if not tool:
                observation = {"error": "Tool not found"}
                show_error("Tool not found")
            else:
                observation = tool["fn"](tool_input)

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