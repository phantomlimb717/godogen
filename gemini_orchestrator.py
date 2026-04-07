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
    "last_plan_content": ""
}

STAGE_ALLOWED_TOOLS = {
    ".gemini/skills/godogen/visual-target.md": ["run_asset_gen", "read_file", "write_file", "list_files", "run_bash_command"],
    ".gemini/skills/godogen/decomposer.md": ["read_file", "write_file", "list_files", "run_bash_command"],
    ".gemini/skills/godogen/scaffold.md": ["read_file", "write_file", "list_files", "run_bash_command", "lookup_godot_api"],
    ".gemini/skills/godogen/asset-planner.md": ["run_asset_gen", "run_tripo3d", "read_file", "write_file", "list_files", "run_bash_command", "lookup_godot_api"],
    ".gemini/skills/godogen/task-execution.md": ["run_asset_gen", "run_tripo3d", "run_visual_qa_analysis", "read_file", "write_file", "list_files", "run_bash_command", "lookup_godot_api"]
}

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

    # Run the autonomous tool loop for the sub-agent until it delivers the final text answer
    while True:
        if response.function_calls:
            function_responses = process_function_calls(response.function_calls, enforce_stage_gates=False)
            response = session.send_message(function_responses)
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
    message = f"We are now entering a new pipeline stage. Please read these instructions carefully before proceeding:\n\n{instructions}"
    # Send the instructions to the model without requiring immediate user action
    response = session.send_message(message)
    print(f"Model response to transition: {response.text}", file=sys.stderr)

def run_autonomous_loop(session: genai.chats.Chat, message: str):
    """Sends a message to the model and manually streams the tool interaction loop."""
    print("\n--- Sending Prompt to Gemini ---", file=sys.stderr)
    print(f"User: {message}\n", file=sys.stderr)

    try:
        # We must manually handle the tool loop to print tool calls to the console in real-time
        response = session.send_message(message)

        while True:
            # Check if the model decided to call any tools
            if response.function_calls:
                function_responses = process_function_calls(response.function_calls)
                # Send the tool output back to the model, which returns the next step
                response = session.send_message(function_responses)
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
    args = parser.parse_args()

    client = get_gemini_client()
    session = create_orchestrator_session(client)

    print("Gemini Orchestrator initialized successfully.", file=sys.stderr)

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
