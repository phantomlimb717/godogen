# Godogen: AI-powered Godot 4 Projects with Gemini

[![Watch the video](https://img.youtube.com/vi/eUz19GROIpY/maxresdefault.jpg)](https://youtu.be/eUz19GROIpY)

[Watch the demos](https://youtu.be/eUz19GROIpY) · [Prompts](demo_prompts.md)

You describe what you want. An AI pipeline designs the architecture, generates the art, writes every line of code, captures screenshots from the running engine, and fixes what doesn't look right. The output is a real Godot 4 project with organized scenes, readable scripts, and proper game architecture. Handles 2D and 3D, runs on commodity hardware.

## How it works

The system is fully decoupled and autonomous. We use a custom standalone **Gemini Orchestrator** (`gemini_orchestrator.py`) written in Python, leveraging the official `google-genai` SDK and the advanced reasoning of the `gemini-3.1-pro-preview-customtools` model.

- **Pipeline State Machine** — The Python orchestrator natively reads your prompt, marches through the game architecture stages (scaffolding, task execution, etc.), and resumes safely if interrupted.
- **Autonomous Tool Integration** — The AI is granted low-level Python tools (file IO, shell execution) allowing it to independently manipulate `.tscn` and `.gd` files and run Godot headless commands to build your game.
- **Forked Sub-Agents** — When looking up massive Godot API documentations or checking screenshots via Visual QA, the orchestrator spawns isolated Gemini sub-agents with dedicated tools to avoid blowing out the main 1M-token context window.
- **Godot 4 output** — real projects with proper scene trees, scripts, and asset organization.
- **Asset generation** — Gemini creates precise references and characters; xAI Grok handles textures and simple objects; Tripo3D converts images to 3D models. Animated sprites use Grok video generation with loop detection.
- **Visual QA closes the loop** — captures actual screenshots from the running game and analyzes them with Gemini. Includes question mode for free-form visual debugging. Catches z-fighting, missing textures, broken physics.

## Getting started

### Prerequisites

- [Godot 4](https://godotengine.org/download/) (headless or editor) on `PATH`
- Python 3.10+ with `pip`
- System packages: `ffmpeg` and `ImageMagick`
- API keys as environment variables:
  - `GOOGLE_API_KEY` — [Google AI Studio](https://aistudio.google.com/), used for Gemini orchestration, text models, and image generation.
  - `XAI_API_KEY` — [xAI Grok](https://console.x.ai/home), used for image/video generation (textures, simple objects)
  - `TRIPO3D_API_KEY` — [Tripo3D](https://platform.tripo3d.ai/), used for image-to-3D model conversion (only needed for 3D games)

The project is built specifically for **native Windows 11 support**. All pipeline tools utilize cross-platform Python scripts (`gemini_orchestrator.py`, `publish.py`, `asset_gen.py`) so you do **not** need WSL2, Git Bash, or MSYS2.

### Windows Setup

1. Install system packages via winget using standard Command Prompt or PowerShell:
   ```powershell
   winget install ffmpeg
   winget install ImageMagick.ImageMagick
   winget install GodotEngine.Godot
   ```
2. Install Python dependencies for the pipeline and the Gemini SDK:
   ```powershell
   pip install -r skills/godogen/tools/requirements.txt
   ```
3. Set your API keys as environment variables (`GOOGLE_API_KEY`, `XAI_API_KEY`, `TRIPO3D_API_KEY`).
4. You are ready to go. No emulation required.

### Beginner's Guide: Running on Windows

If you are new to the command line, follow these exact steps to build your first game on Windows 11.

1. **Open PowerShell as Administrator**
   Click the Start menu, type `powershell`, right-click it, and select **"Run as Administrator"**.
2. **Install the required software**
   Copy and paste this block into your PowerShell window, then press Enter:
   ```powershell
   winget install ffmpeg
   winget install ImageMagick.ImageMagick
   winget install GodotEngine.Godot
   ```
3. **Set your API Keys**
   You need a free [Google AI Studio key](https://aistudio.google.com/) for Gemini, an [xAI Grok key](https://console.x.ai/home) for textures, and a [Tripo3D key](https://platform.tripo3d.ai/) for 3D models.
   In PowerShell, set them like this (replace the text inside the quotes with your actual keys):
   ```powershell
   $env:GOOGLE_API_KEY="your-google-api-key"
   $env:XAI_API_KEY="your-xai-api-key"
   $env:TRIPO3D_API_KEY="your-tripo3d-api-key"
   ```
4. **Download this repository and install Python dependencies**
   ```powershell
   git clone https://github.com/your-username/godogen.git
   cd godogen
   pip install -r skills/godogen/tools/requirements.txt
   ```
5. **Create your game folder**
   We need to publish the AI orchestrator into a new folder on your Desktop where your game will live:
   ```powershell
   python publish.py $HOME\Desktop\MyFirstGame
   ```
6. **Start the AI Orchestrator**
   Navigate to your new game folder and tell the Gemini AI what to build:
   ```powershell
   cd $HOME\Desktop\MyFirstGame
   python gemini_orchestrator.py --prompt "A 2D platformer game where a frog collects coins and avoids spikes"
   ```
7. **Watch it build!**
   The terminal will begin scrolling rapidly as Gemini writes code, creates `.tscn` Godot scenes, and generates assets. You will see outputs like `-> Agent Executing: write_file`. Let it run until it says it is finished. You can open the generated `project.godot` file in the Godot engine at any time to play your game.

### Create a game project (Advanced)

This repo is the skill development source. To start making a game, run `publish.py` to compile the orchestrator and all the agentic instructions into a fresh project folder:

```bash
python publish.py ~/my-game
python publish.py --force ~/my-game  # clean existing target before publishing
```

This sets up the target directory with the `.gemini/skills/` toolset, copies the `gemini_orchestrator.py` backbone, and initializes a git repo.

To kick off the autonomous generation, navigate to that folder and feed a prompt to the orchestrator:
```bash
cd ~/my-game
python gemini_orchestrator.py --prompt "A 3D snowboarding game with procedural terrain"
```
The Gemini orchestrator will take over, streaming tool executions and generating your game directly to disk.

### Running on a VM

A single generation run can take several hours. Running on a cloud VM keeps your local machine free and gives the pipeline a GPU for Godot's screenshot capture. A basic GCE instance with a T4 or L4 GPU works well.

## Is Claude Code still supported?

While the initial versions of this repository relied on Claude Code, the project has fully migrated to the standalone **Gemini Orchestrator**. This custom Python implementation allows us to maintain tight control over tool routing, context-forking, and model optimization (`gemini-3.1-pro-preview-customtools`) natively, bypassing Claude Code's proprietary plugin system.

## Roadmap

- Explore C# as GDScript alternative
- Publish a full game end-to-end as a public demo
- Explore Bevy Engine as Godot alternative

## Changelog

**2026-04-03 — Single-context architecture** (current)
- Merged task executor into godogen — full pipeline runs in one 1M-token context window
- Added godot-api skill (forked, Sonnet) for Godot class API lookup
- Added visual-qa skill (forked) with Gemini Flash, Claude vision, and question mode
- Risk-first decomposition replaces task DAG
- Android debug APK export

**2026-03-25 — xAI Grok video**
- Added xAI Grok video generation for animated sprites (ref → pose → video → frames → loop trim)
- Background removal rewritten with BiRefNet multi-signal matting
- macOS support, native channel status updates

**2026-03-09 — Initial release**
- Two-skill architecture: godogen orchestrator + godot-task executor (forked)
- Gemini image generation, Tripo3D for 3D models
- Visual QA via Gemini Flash
- Screenshot and video capture, presentation video
- GDScript reference system with lazy two-tier API lookup

Follow progress: [@alex_erm](https://x.com/alex_erm)
