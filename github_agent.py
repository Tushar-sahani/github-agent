import os
import json
import subprocess
from dotenv import load_dotenv
from openai import OpenAI

# -------------------------
# Load environment variables
# -------------------------
load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

MAX_STEPS = 15

# -------------------------
# Safety guardrails
# -------------------------

BLOCKED_COMMANDS = [
    "rm -rf",
    "shutdown",
    "reboot",
    "mkfs",
    ":(){:|:&};:"
]


def is_safe_command(command: str):
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return False
    return True


# -------------------------
# TOOLS
# -------------------------

def run_command(command: str):

    if not is_safe_command(command):
        return {"error": "Blocked unsafe command"}

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

    command = f"gh repo create {repo_name} --public --source=. --push"

    return run_command(command)


# -------------------------
# TOOL REGISTRY
# -------------------------

TOOLS = {
    "run_command": {
        "fn": run_command,
        "description": "Execute terminal commands"
    },
    "create_repo": {
        "fn": create_repo,
        "description": "Create GitHub repository and push code"
    }
}

# -------------------------
# SYSTEM PROMPT
# -------------------------

SYSTEM_PROMPT = """
You are an AI Assistent experties in the automating the github related any user query.
You are best in pushing the code to github account. 

You operate using these steps:

PLAN
ACTION
OBSERVE
OUTPUT

Rules:

- Always PLAN before ACTION
- Only call tools that are available
- Wait for OBSERVE before continuing
- Return ONLY ONE JSON object per response
- Finish with OUTPUT

Output JSON format:

{
 "step":"plan | action | observe | output",
 "content":"reasoning",
 "function":"tool_name_if_action",
 "input":"tool_input"
}

Available tools:

run_command
create_repo
"""

# -------------------------
# Agent memory
# -------------------------

messages = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

memory = []

# -------------------------
# AGENT LOOP
# -------------------------

def run_agent(user_query):

    messages.append({"role": "user", "content": user_query})

    for step in range(MAX_STEPS):

        print(f"\n--- Step {step+1} ---")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )

        content = response.choices[0].message.content.strip()

        try:
            parsed = json.loads(content)
        except Exception:
            print("❌ Invalid JSON returned by model:")
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

            print("🧠 PLAN:", parsed.get("content"))
            continue

        # -------------------------
        # ACTION
        # -------------------------

        if step_type == "action":

            tool_name = parsed.get("function")
            tool_input = parsed.get("input")

            print(f"⚙️ ACTION: {tool_name} -> {tool_input}")

            tool = TOOLS.get(tool_name)

            if not tool:
                observation = {"error": "Tool not found"}
            else:
                observation = tool["fn"](tool_input)

            memory.append(observation)

            print("👀 OBSERVE:", observation)

            observe_msg = {
                "step": "observe",
                "output": observation
            }

            messages.append({
                "role": "assistant",
                "content": json.dumps(observe_msg)
            })

            continue

        # -------------------------
        # OUTPUT
        # -------------------------

        if step_type == "output":

            print("\n✅ RESULT:", parsed.get("content"))
            break


# -------------------------
# CLI
# -------------------------

if __name__ == "__main__":

    print("\n🚀 GitHub Automation Agent Ready")
    print("Type 'exit' to quit\n")

    while True:

        query = input("> ")

        if query.lower() == "exit":
            print("Bye!")
            break

        run_agent(query)