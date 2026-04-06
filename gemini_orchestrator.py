#!/usr/bin/env python3
"""Gemini Orchestrator for Godogen

This script serves as a standalone alternative to Claude Code for orchestrating
the Godogen AI game development pipeline using Google Gemini Pro.
"""

import os
import sys
import argparse
from pathlib import Path
from google import genai
from google.genai import types

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
    cmd = ["python", "skills/godogen/tools/asset_gen.py", command, "--prompt", prompt, "-o", output]

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
    cmd = ["python", "skills/godogen/tools/asset_gen.py", "glb", "--image", image_path, "-o", output_path, "--quality", quality]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return f"Success: {result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error running tripo3d conversion: {e.stderr}"

def lookup_godot_api(query: str) -> str:
    """Query the Godot API Documentation."""
    # Spawn a separate Gemini API call (forked context) for lookup
    client = get_gemini_client()
    instructions = load_stage_instructions("skills/godot-api/SKILL.md")
    response = client.models.generate_content(
        model="gemini-3.1-pro-preview-customtools",
        contents=f"Lookup Godot API query: {query}",
        config=types.GenerateContentConfig(
            system_instruction=instructions,
            temperature=0.0
        )
    )
    return response.text

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
            dirs[:] = [d for d in dirs if not d.startswith('.')]
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

def run_visual_qa_analysis(mode: str, reference_path: str = None, game_screenshots: list[str] = None, question: str = None) -> str:
    """Run visual QA on screenshots compared to a reference image."""
    cmd = ["python", "skills/visual-qa/scripts/visual_qa.py"]
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

def create_orchestrator_session(client: genai.Client) -> genai.chats.Chat:
    """Create the main orchestrator ChatSession."""
    model_id = "gemini-3.1-pro-preview-customtools" # Advanced reasoning + context window optimized for custom tools/bash agentic workflows

    # Load initial global instructions from SKILL.md
    base_instructions = load_stage_instructions("skills/godogen/SKILL.md")

    # Register the tools with Gemini
    tools = [
        run_asset_gen, run_tripo3d, lookup_godot_api, run_visual_qa_analysis,
        read_file, write_file, list_files, run_bash_command
    ]

    config = types.GenerateContentConfig(
        system_instruction=base_instructions,
        temperature=0.0,
        tools=tools
    )

    return client.chats.create(model=model_id, config=config)

def transition_to_stage(session: genai.chats.Chat, stage_file: str):
    """Load new stage instructions and send them to the model."""
    print(f"Transitioning to stage: {stage_file}", file=sys.stderr)
    instructions = load_stage_instructions(stage_file)
    message = f"We are now entering a new pipeline stage. Please read these instructions carefully before proceeding:\n\n{instructions}"
    # Send the instructions to the model without requiring immediate user action
    response = session.send_message(message)
    print(f"Model response to transition: {response.text}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="Gemini CLI Orchestrator for Godogen")
    parser.add_argument("--prompt", type=str, help="The natural language description of the game to build")
    args = parser.parse_args()

    client = get_gemini_client()
    session = create_orchestrator_session(client)

    print("Gemini Orchestrator initialized successfully.", file=sys.stderr)

    if args.prompt:
        print(f"Received prompt: {args.prompt}", file=sys.stderr)
        # TODO: Send initial prompt to session and begin pipeline

if __name__ == "__main__":
    main()
