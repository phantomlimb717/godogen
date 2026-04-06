# Visual Quality Assurance

Analyze game screenshots against the visual reference. Runs using the `run_visual_qa_analysis` tool.

## Static Mode

For scenes without meaningful motion (decoration, terrain, UI). Two images: reference + one game screenshot.

```python
run_visual_qa_analysis(
    mode="static",
    reference_path="reference.png",
    game_screenshots=["screenshots/{task}/frame0003.png"],
    question="Goal: ..., Requirements: ..., Verify: ..."
)
```

Pick a representative frame (not the first — often has init artifacts).

## Dynamic Mode

For scenes with motion, animation, or physics. Reference + frame sequence at **2 FPS cadence** — every Nth frame where N = capture_fps / 2.

```python
# Example: For dynamic analysis, you can pass a list of selected frame paths
run_visual_qa_analysis(
    mode="dynamic",
    reference_path="reference.png",
    game_screenshots=["screenshots/{task}/frame0005.png", "screenshots/{task}/frame0010.png"],
    question="Goal: ..., Requirements: ..., Verify: ..."
)
```

## Question Mode

For debugging and investigation — ask any question about screenshots without needing a reference image.

```python
run_visual_qa_analysis(
    mode="question",
    game_screenshots=["screenshots/{task}/frame0005.png"],
    question="Are any surfaces showing magenta or default grey material?"
)

run_visual_qa_analysis(
    mode="question",
    game_screenshots=["screenshots/{task}/frame0001.png", "screenshots/{task}/frame0010.png", "screenshots/{task}/frame0020.png"],
    question="Does the enemy patrol path form a loop?"
)

run_visual_qa_analysis(
    mode="question",
    game_screenshots=["screenshots/{task}/frame0001.png", "screenshots/{task}/frame0005.png"],
    question="The door should open when player approaches. Does it? InteractionSystem triggers at 2m, door uses AnimationPlayer."
)
```

## Context

Pass the task's **Goal**, **Requirements**, and **Verify** from PLAN.md as freeform text. The QA has two objectives:
1. **Quality verification (primary):** visual defects, bugs, implementation shortcuts — problems regardless of what the task asked for.
2. **Goal verification (secondary):** does the output match what was requested?

## Common

- Output: markdown report with verdict (`pass`/`fail`/`warning`), reference match, goal assessment, per-issue details
- Severity: `major`/`minor` = must fix; `note` = cosmetic, can ship
- Debug log appended to `.vqa.log` (JSONL: query, files, output)
- Question mode output goes to stdout — read directly
