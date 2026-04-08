#!/usr/bin/env python3
"""Gemini Orchestrator for Godogen

This script serves as a standalone alternative to Claude Code for orchestrating
the Godogen AI game development pipeline using Google Gemini Pro.
"""

# ==========================================
# Cache stability invariants
# ==========================================
# The system prompt and tool declarations must be byte-identical
# across every turn within a single run.
# Any interpolated timestamp, random ID, run-specific path,
# or reordered tool declaration invalidates the cache for the rest of the run.
# Any future edit that breaks this silently regresses API cost.
# ==========================================

MODEL_CONFIG = {
    "main_orchestrator": "gemini-3.1-pro-preview-customtools",
    "visual_qa_fork": "gemini-3.1-flash-lite-preview",
    "godot_api_lookup_fork": "gemini-3.1-flash-lite-preview"
}

import os
import sys
import argparse
import datetime
import difflib
from pathlib import Path
from google import genai
from google.genai import types

ORCHESTRATOR_STATE = {
    "current_stage": "initialization",
    "last_plan_content": "",
    "current_todo_task": None,
    "task_turn_count": 0,
    "task_file_writes": {},
    "reflection_triggered_for_task": False,
    "trigger_reflection": False,
    "turn_counter": 0,
    "estimated_cost_cents": 0.0,
    "warned_missing_usage": False
}

STAGE_ALLOWED_TOOLS = {
    ".gemini/skills/godogen/visual-target.md": ["run_asset_gen", "read_file", "write_file", "list_files", "run_bash_command"],
    ".gemini/skills/godogen/decomposer.md": ["read_file", "write_file", "list_files", "run_bash_command"],
    ".gemini/skills/godogen/scaffold.md": ["read_file", "write_file", "list_files", "run_bash_command", "lookup_godot_api"],
    ".gemini/skills/godogen/asset-planner.md": ["run_asset_gen", "run_tripo3d", "read_file", "write_file", "list_files", "run_bash_command", "lookup_godot_api"],
    ".gemini/skills/godogen/task-execution.md": ["run_asset_gen", "run_tripo3d", "run_visual_qa_analysis", "read_file", "write_file", "list_files", "run_bash_command", "lookup_godot_api"],
    ".gemini/skills/godogen/amend.md": ["run_asset_gen", "run_tripo3d", "run_visual_qa_analysis", "read_file", "write_file", "list_files", "run_bash_command", "lookup_godot_api"]
}

def get_current_task_info():
    """Parses TODO.md for current task name and task index."""
    try:
        todo_path = Path("TODO.md")
        if not todo_path.exists():
            return None, None

        content = todo_path.read_text()
        lines = [line.strip() for line in content.splitlines()]

        task_name = None
        in_current_task = False
        for line in lines:
            if line.lower() == "## current task":
                in_current_task = True
                continue
            if in_current_task:
                if line and not line.startswith("##"):
                    task_name = line
                    break
                elif line.startswith("##"):
                    break

        in_remaining_tasks = False
        remaining_count = 0
        for line in lines:
            if line.lower() == "## remaining tasks":
                in_remaining_tasks = True
                continue
            if in_remaining_tasks:
                if line.startswith("##"):
                    break
                # Only count non-empty lines that look like list items
                if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                    remaining_count += 1

        if task_name:
            task_index = f"1/{remaining_count + 1}"
            return task_name, task_index
        else:
            return None, None
    except Exception:
        return None, None

def print_status_line():
    """Constructs and prints the status line to stderr."""
    stage_path = ORCHESTRATOR_STATE.get("current_stage", "unknown")
    stage_name = os.path.basename(stage_path).replace(".md", "")

    task_name, task_index = get_current_task_info()
    if task_name and task_index:
        task_str = f"Task {task_index} ({task_name})"
    else:
        task_str = "Task: n/a"

    turn_counter = ORCHESTRATOR_STATE.get("turn_counter", 0)
    cost_cents = ORCHESTRATOR_STATE.get("estimated_cost_cents", 0.0)
    cost_dollars = cost_cents / 100.0

    status_line = f"[STATUS] Stage: {stage_name} | {task_str} | Turn {turn_counter} | Cost: ${cost_dollars:.2f}"
    print(status_line, file=sys.stderr)

def accumulate_gemini_cost(response, model_id: str):
    """Accumulates cost based on token usage in the Gemini API response."""
    if not hasattr(response, "usage_metadata") or response.usage_metadata is None:
        if not ORCHESTRATOR_STATE.get("warned_missing_usage"):
            print("Warning: Gemini API response is missing usage_metadata. Cost tracking may be incomplete.", file=sys.stderr)
            ORCHESTRATOR_STATE["warned_missing_usage"] = True
        return

    usage = response.usage_metadata
    prompt_tokens = getattr(usage, "prompt_token_count", 0)
    candidates_tokens = getattr(usage, "candidates_token_count", 0)

    # Rates per million tokens (in dollars)
    rates = {
        "gemini-3.1-pro-preview-customtools": {"input": 1.25, "output": 5.00},
        "gemini-3.1-flash-lite-preview": {"input": 0.10, "output": 0.40}
    }

    if model_id in rates:
        input_rate = rates[model_id]["input"]
        output_rate = rates[model_id]["output"]

        cost_dollars = (prompt_tokens * input_rate + candidates_tokens * output_rate) / 1_000_000
        cost_cents = cost_dollars * 100
        ORCHESTRATOR_STATE["estimated_cost_cents"] += cost_cents

def get_gemini_client() -> genai.Client:
    """Initialize and return the Gemini Client."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    return genai.Client(api_key=api_key)

def load_stage_instructions(filepath: str) -> str:
    """Read a specific markdown file to load pipeline stage instructions."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Instruction file {filepath} not found.")
    return path.read_text()

import subprocess
import json
import re

def run_asset_gen(command: str, prompt: str, image: str = None, duration: int = None, size: str = "1K", aspect_ratio: str = "1:1", output: str = "assets/output.png") -> str:
    """Run the asset generator (images or videos)."""
    cmd = ["python", ".gemini/skills/godogen/tools/asset_gen.py", command, "--prompt", prompt, "-o", output]

    if image:
        cmd.extend(["--image", image])
    if duration and command == "video":
        cmd.extend(["--duration", str(duration)])
    if command == "image":
        cmd.extend(["--size", size, "--aspect-ratio", aspect_ratio])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse the cost from the JSON output
        match = re.search(r'\{.*"cost_cents":\s*(\d+).*\}', result.stdout)
        if match:
            try:
                cost_cents = int(match.group(1))
                ORCHESTRATOR_STATE["estimated_cost_cents"] += cost_cents
            except ValueError:
                pass

        return f"Success: {result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error running asset_gen.py: {e.stderr}"

def run_tripo3d(image_path: str, output_path: str, quality: str = "default") -> str:
    """Convert an image to a GLB 3D model using Tripo3D."""
    # Note: Using tripo3d.py natively or asset_gen.py glb proxy depending on repo setup.
    # The review implies tripo3d.py should be called directly.
    cmd = ["python", ".gemini/skills/godogen/tools/tripo3d.py", "glb", "--image", image_path, "-o", output_path, "--quality", quality]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return f"Success: {result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error running tripo3d conversion: {e.stderr}"

def process_function_calls(function_calls, enforce_stage_gates: bool = True) -> list:
    """Helper method to dynamically map and execute function tools based on model requests."""
    function_responses = []

    tool_map = {
        "run_asset_gen": run_asset_gen,
        "run_tripo3d": run_tripo3d,
        "run_visual_qa_analysis": run_visual_qa_analysis,
        "read_file": read_file,
        "write_file": write_file,
        "list_files": list_files,
        "run_bash_command": run_bash_command
    }

    for function_call in function_calls:
        func_name = function_call.name
        args = {k: v for k, v in (function_call.args or {}).items() if v is not None}

        print(f"-> Agent Executing: {func_name}({args})", file=sys.stderr)

        if func_name == "write_file" and "filepath" in args:
            filepath = args["filepath"]
            ORCHESTRATOR_STATE["task_file_writes"][filepath] = ORCHESTRATOR_STATE["task_file_writes"].get(filepath, 0) + 1

        if enforce_stage_gates:
            current_stage = ORCHESTRATOR_STATE["current_stage"]
            if current_stage in STAGE_ALLOWED_TOOLS and func_name not in STAGE_ALLOWED_TOOLS[current_stage]:
                allowed_tools = STAGE_ALLOWED_TOOLS[current_stage]
                result = f"Error: Tool '{func_name}' is not permitted in the current stage '{current_stage}'. Allowed tools: {allowed_tools}. Do not advance the pipeline yourself; complete this stage's criteria so the orchestrator can advance."
                function_responses.append(
                    types.Part.from_function_response(
                        name=func_name,
                        response={"result": result}
                    )
                )
                continue

        func_to_call = tool_map.get(func_name)
        try:
            if func_name == "lookup_godot_api":
                result = lookup_godot_api(**args)
            elif func_to_call:
                result = func_to_call(**args)
            else:
                result = f"Error: Tool {func_name} not found."
        except Exception as e:
            result = f"Error executing {func_name}: {str(e)}"

        function_responses.append(
            types.Part.from_function_response(
                name=func_name,
                response={"result": result}
            )
        )
    return function_responses

def lookup_godot_api(query: str, model: str = None) -> str:
    """Query the Godot API Documentation."""
    model_id = model or MODEL_CONFIG["godot_api_lookup_fork"]
    # Spawn a separate Gemini API call (forked context) for lookup
    client = get_gemini_client()
    instructions = load_stage_instructions(".gemini/skills/godot-api/SKILL.md")

    # Sub-agent needs file searching tools to read the documentation
    tools = sorted([read_file, list_files, run_bash_command], key=lambda f: f.__name__)

    config = types.GenerateContentConfig(
        system_instruction=instructions,
        temperature=0.0,
        tools=tools
    )

    session = client.chats.create(model=model_id, config=config)
    response = session.send_message(f"Lookup Godot API query: {query}")
    accumulate_gemini_cost(response, model_id)

    # Run the autonomous tool loop for the sub-agent until it delivers the final text answer
    while True:
        if response.function_calls:
            function_responses = process_function_calls(response.function_calls, enforce_stage_gates=False)
            response = session.send_message(function_responses)
            accumulate_gemini_cost(response, model_id)
        else:
            if response.text:
                return response.text
            break

    return "API Lookup Failed to provide a textual answer."

def read_file(filepath: str) -> str:
    """Reads the content of a specific file."""
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Error: File {filepath} not found."
        return path.read_text()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(filepath: str, content: str) -> str:
    """Writes or overwrites a file with the given content."""
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def list_files(directory: str = ".") -> str:
    """Lists all files and directories under the given directory."""
    try:
        result = []
        for root, dirs, files in os.walk(directory):
            # Skip hidden directories like .git and .gemini
            dirs[:] = sorted([d for d in dirs if not d.startswith('.')])
            files = sorted(files)
            try:
                rel_parts = Path(root).relative_to(directory).parts
                level = len(rel_parts)
            except ValueError:
                level = 0

            indent = ' ' * 4 * (level)
            result.append(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                result.append(f"{subindent}{f}")
        return "\n".join(result)
    except Exception as e:
        return f"Error listing files: {str(e)}"

def run_bash_command(command: str) -> str:
    """Runs a given bash command in the terminal."""
    try:
        # Use shell=True to allow complex commands (e.g. piping, logical operators)
        result = subprocess.run(command, capture_output=True, text=True, shell=True)

        output = f"Exit code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"

def run_visual_qa_analysis(mode: str, reference_path: str = None, game_screenshots: list[str] = None, question: str = None, model: str = None) -> str:
    """Run visual QA on screenshots compared to a reference image."""
    model_id = model or MODEL_CONFIG["visual_qa_fork"]
    cmd = ["python", ".gemini/skills/visual-qa/scripts/visual_qa.py", "--model", model_id]
    if question:
        cmd.extend(["--question", question])
        if game_screenshots:
            cmd.extend(game_screenshots)
    else:
        if reference_path:
            cmd.append(reference_path)
        if game_screenshots:
            cmd.extend(game_screenshots)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return f"Visual QA Output:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Visual QA Error:\n{e.stderr}"

def record_stage_completion(stage_file: str):
    """Record that a stage has successfully completed."""
    state_dir = Path(".godogen_state")
    state_dir.mkdir(parents=True, exist_ok=True)
    log_file = state_dir / "stage_history.jsonl"

    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "completed_stage": stage_file
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(record) + "\n")

def create_orchestrator_session(client: genai.Client, model_id: str = None) -> genai.chats.Chat:
    """Create the main orchestrator ChatSession."""
    model_id = model_id or MODEL_CONFIG["main_orchestrator"]

    # Load initial global instructions from SKILL.md
    base_instructions = load_stage_instructions(".gemini/skills/godogen/SKILL.md")

    house_rules_path = Path("HOUSE_RULES.md")
    if house_rules_path.exists():
        house_rules_content = house_rules_path.read_text().strip()
        if house_rules_content:
            base_instructions += f"\n\n---\n\n## Project House Rules\n\nThe following rules apply for the entire duration of this project. Follow them in every stage and every task:\n\n{house_rules_content}"

    # Register the tools with Gemini
    tools = sorted([
        run_asset_gen, run_tripo3d, lookup_godot_api, run_visual_qa_analysis,
        read_file, write_file, list_files, run_bash_command
    ], key=lambda f: f.__name__)

    config = types.GenerateContentConfig(
        system_instruction=base_instructions,
        temperature=0.0,
        tools=tools
    )

    return client.chats.create(model=model_id, config=config)

def transition_to_stage(session: genai.chats.Chat, stage_file: str):
    """Load new stage instructions and send them to the model."""
    plan_path = Path("PLAN.md")
    current_plan_content = plan_path.read_text() if plan_path.exists() else ""

    last_plan_content = ORCHESTRATOR_STATE["last_plan_content"]

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    diff_lines = list(difflib.unified_diff(
        last_plan_content.splitlines(),
        current_plan_content.splitlines(),
        fromfile="PLAN.md (previous)",
        tofile="PLAN.md (current)",
        lineterm=""
    ))

    diff_output = "\n".join(diff_lines) if diff_lines else "No changes to PLAN.md."

    print(f"[{timestamp}] Stage Transition: {stage_file}", file=sys.stdout)
    print(f"--- PLAN.md Changes ---\n{diff_output}\n-----------------------", file=sys.stdout)

    # Handle TODO.md initialization for task-execution stage
    todo_msg_addition = ""
    if stage_file.endswith("task-execution.md"):
        todo_path = Path("TODO.md")
        if not todo_path.exists() and plan_path.exists():
            tasks = []
            in_tasks_section = False
            for line in current_plan_content.splitlines():
                # Detect sections that usually contain tasks
                if line.strip().lower() in ["## tasks", "### tasks", "## risk tasks", "### risk tasks", "## main build", "### main build"]:
                    in_tasks_section = True
                    continue
                elif line.startswith("#") and in_tasks_section:
                    # Leaving a task section
                    if not line.startswith("## ") and not line.startswith("### "):
                        in_tasks_section = False
                    # But if it's another task-like section, we keep scanning.
                    # A more robust way: collect headers that look like tasks

                # If we are in a section or just scanning for headers
                # We'll just grab all ### or ## headers under task sections.
                if in_tasks_section and (line.startswith("### ") or line.startswith("## ")):
                    # Ignore the section headers themselves
                    if line.strip().lower() not in ["## tasks", "### tasks", "## risk tasks", "### risk tasks", "## main build", "### main build"]:
                        tasks.append(line.lstrip("#").strip())

            if tasks:
                current_task = tasks[0]
                remaining_tasks = tasks[1:]

                todo_content = f"# TODO\n\n## Current task\n{current_task}\n\n## Steps\n\n## Done (this task)\n\n## Remaining tasks\n"
                for i, task in enumerate(remaining_tasks, 1):
                    todo_content += f"{i}. {task}\n"

                todo_path.write_text(todo_content)
                print(f"[{timestamp}] Initialized TODO.md from PLAN.md", file=sys.stdout)

        todo_msg_addition = "\n\nTODO.md has been initialized and you must use it as your active execution tracker."

    # Record the stage transition
    state_dir = Path(".godogen_state")
    state_dir.mkdir(parents=True, exist_ok=True)
    log_file = state_dir / "stage_history.jsonl"

    transition_record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "entered_stage": stage_file,
        "exited_stage": ORCHESTRATOR_STATE.get("current_stage")
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(transition_record) + "\n")

    ORCHESTRATOR_STATE["current_stage"] = stage_file
    ORCHESTRATOR_STATE["last_plan_content"] = current_plan_content

    print(f"Transitioning to stage: {stage_file}", file=sys.stderr)
    instructions = load_stage_instructions(stage_file)
    message = f"We are now entering a new pipeline stage. Please read these instructions carefully before proceeding:\n\n{instructions}{todo_msg_addition}"
    # Send the instructions to the model without requiring immediate user action
    response = session.send_message(message)
    accumulate_gemini_cost(response, MODEL_CONFIG["main_orchestrator"])
    print(f"Model response to transition: {response.text}", file=sys.stderr)

def run_autonomous_loop(session: genai.chats.Chat, message: str):
    """Sends a message to the model and manually streams the tool interaction loop."""
    print("\n--- Sending Prompt to Gemini ---", file=sys.stderr)
    print(f"User: {message}\n", file=sys.stderr)

    reflection_prompt = (
        "REFLECTION TRIGGER: You have been working on the same task for several turns without clear progress. "
        "Take a moment to step back and reconsider. Questions to ask yourself: "
        "First, what is the simplest version of this task that would pass verification? Have you tried that approach, "
        "or have you been pursuing a more complex approach that may not be necessary? "
        "Second, are you debugging the right thing? The error message you keep seeing might be pointing at a symptom "
        "rather than the root cause. Consider whether the failure is in your implementation code, your test code, "
        "or your assumptions about how the underlying system works. "
        "Third, is there a simpler test you could write that would verify the same behavior with less mechanism? "
        "Fourth, if you genuinely cannot make progress on this task, you may mark it as 'blocked' in TODO.md "
        "with a one-line explanation and proceed to the next task. A blocked task is acceptable; an infinite loop is not. "
        "The user can address blocked tasks in a future amendment. "
        "After this reflection, update TODO.md with your conclusion and proceed accordingly."
    )

    try:
        # We must manually handle the tool loop to print tool calls to the console in real-time
        response = session.send_message(message)
        accumulate_gemini_cost(response, MODEL_CONFIG["main_orchestrator"])

        while True:
            ORCHESTRATOR_STATE["turn_counter"] += 1
            print_status_line()

            # Check if the model decided to call any tools
            if response.function_calls:
                function_responses = process_function_calls(response.function_calls)

                # Reflection check
                current_stage = ORCHESTRATOR_STATE.get("current_stage", "")
                if current_stage.endswith("task-execution.md") or current_stage.endswith("amend.md"):
                    todo_path = Path("TODO.md")
                    if todo_path.exists():
                        todo_content = todo_path.read_text().splitlines()
                        parsed_task = None
                        for i, line in enumerate(todo_content):
                            if line.strip().lower() == "## current task":
                                if i + 1 < len(todo_content):
                                    parsed_task = todo_content[i + 1].strip()
                                break

                        if parsed_task:
                            if parsed_task == ORCHESTRATOR_STATE["current_todo_task"]:
                                ORCHESTRATOR_STATE["task_turn_count"] += 1
                            else:
                                ORCHESTRATOR_STATE["current_todo_task"] = parsed_task
                                ORCHESTRATOR_STATE["task_turn_count"] = 1
                                ORCHESTRATOR_STATE["task_file_writes"] = {}
                                ORCHESTRATOR_STATE["reflection_triggered_for_task"] = False

                            turn_count = ORCHESTRATOR_STATE["task_turn_count"]
                            writes_dict = ORCHESTRATOR_STATE["task_file_writes"]
                            max_writes = max(writes_dict.values()) if writes_dict else 0

                            if (turn_count > 5 or max_writes > 3) and not ORCHESTRATOR_STATE["reflection_triggered_for_task"]:
                                print(f"[REFLECTION TRIGGER] Task '{parsed_task}' has been active for {turn_count} turns. Forcing reflection.", file=sys.stderr)
                                ORCHESTRATOR_STATE["trigger_reflection"] = True
                                ORCHESTRATOR_STATE["reflection_triggered_for_task"] = True

                if ORCHESTRATOR_STATE.get("trigger_reflection"):
                    reflection_part = types.Part(text=reflection_prompt)
                    function_responses.append(reflection_part)
                    ORCHESTRATOR_STATE["trigger_reflection"] = False

                # Send the tool output back to the model, which returns the next step
                response = session.send_message(function_responses)
                accumulate_gemini_cost(response, MODEL_CONFIG["main_orchestrator"])
            else:
                # No tool calls made, the agent is responding with final text.
                if response.text:
                    print(f"Gemini: {response.text}\n", file=sys.stderr)
                break

    except KeyboardInterrupt:
        print("\n[!] Execution paused by user (KeyboardInterrupt). Exiting loop cleanly.", file=sys.stderr)
        raise
    except Exception as e:
        print(f"\n[!] Unexpected error in autonomous loop: {e}", file=sys.stderr)
        raise

def main():
    parser = argparse.ArgumentParser(description="Gemini CLI Orchestrator for Godogen")
    parser.add_argument("--prompt", type=str, help="The natural language description of the game to build")
    parser.add_argument("--amend", type=str, help="The description of what to add or fix in an existing project")
    args = parser.parse_args()

    if args.prompt and args.amend:
        print("Error: --prompt and --amend are mutually exclusive. Use one or the other.", file=sys.stderr)
        sys.exit(1)

    client = get_gemini_client()
    session = create_orchestrator_session(client)

    print("Gemini Orchestrator initialized successfully.", file=sys.stderr)

    if args.amend:
        # Verify project exists
        required_files = ["reference.png", "PLAN.md", "STRUCTURE.md"]
        for f in required_files:
            if not Path(f).exists():
                print(f"Error: amend mode requires existing project. Missing: {f}", file=sys.stderr)
                sys.exit(1)

        # Enter amend mode
        transition_to_stage(session, ".gemini/skills/godogen/amend.md")
        run_autonomous_loop(session, f"AMENDMENT REQUEST: {args.amend}\n\nThe project at this directory is an existing godogen project. Treat all existing files as ground truth. Read PLAN.md to understand the current state. Add a new 'Amendments' section to PLAN.md with the requested changes broken into tasks, then execute only those new tasks. Do NOT re-verify or re-run any task that is already marked complete in PLAN.md.")

        # Record amendment in stage history
        state_dir = Path(".godogen_state")
        state_dir.mkdir(parents=True, exist_ok=True)
        amendment_record = {
            "timestamp": datetime.datetime.now().isoformat(),
            "amendment": args.amend,
            "completed": True
        }
        with open(state_dir / "stage_history.jsonl", "a") as f:
            f.write(json.dumps(amendment_record) + "\n")

        return

    # Define the core Godogen pipeline stages
    pipeline_stages = [
        {"file": ".gemini/skills/godogen/visual-target.md", "artifact": "reference.png"},
        {"file": ".gemini/skills/godogen/decomposer.md", "artifact": "PLAN.md"},
        {"file": ".gemini/skills/godogen/scaffold.md", "artifact": "STRUCTURE.md"},
        {"file": ".gemini/skills/godogen/asset-planner.md", "artifact": "ASSETS.md"},
        {"file": ".gemini/skills/godogen/task-execution.md", "artifact": None} # Task execution runs until completion
    ]

    if args.prompt:
        # Initial kick-off
        run_autonomous_loop(session, f"New Game Request: {args.prompt}\n\nPlease begin the pipeline.")

    # Execute Pipeline State Machine with resumability
    for stage in pipeline_stages:
        artifact = stage["artifact"]

        # Resumability check: if artifact exists, verify it completed
        if artifact and Path(artifact).exists():
            log_file = Path(".godogen_state/stage_history.jsonl")
            if log_file.exists():
                completed = False
                with open(log_file, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        record = json.loads(line)
                        if record.get("completed_stage") == stage["file"]:
                            completed = True
                            break
                if completed:
                    print(f"Found {artifact} and stage completion record. Skipping {stage['file']} stage.", file=sys.stderr)
                    continue
                else:
                    print(f"Warning: Artifact {artifact} exists but no record of stage {stage['file']} completion, re-running stage to ensure consistency.", file=sys.stderr)
            else:
                print(f"Found {artifact}. Skipping {stage['file']} stage.", file=sys.stderr)
                continue

        # Enter the stage
        transition_to_stage(session, stage["file"])

        # Prompt the model to execute the current stage
        run_autonomous_loop(session, f"Please execute the current stage based on the instructions just provided. Let me know when you are finished.")

        # Record completion
        record_stage_completion(stage["file"])

if __name__ == "__main__":
    main()
