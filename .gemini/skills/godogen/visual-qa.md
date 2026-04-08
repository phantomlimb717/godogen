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

## Question Mode (Two-Step Descriptive Pattern)

For debugging and investigation, never ask leading questions (e.g., yes/no questions, hypotheses baked in). Instead, use a two-step descriptive pattern:

1. **Step One (VQA Observation):** Ask the VQA model to describe exactly what it sees in each frame neutrally (position, size, rotation, visible details, frame-to-frame differences).
2. **Step Two (Python Judgment):** Compare the VQA descriptions deterministically against expected behavior from PLAN.md in Python to decide pass/fail.

### Bad Pattern (Before)
Leading questions prime the model and incentivize hallucination.

```python
run_visual_qa_analysis(
    mode="question",
    game_screenshots=["screenshots/{task}/frame0001.png", "screenshots/{task}/frame0010.png"],
    question="Does the green square (player) change its scale or rotation across these frames, indicating idle, run, and jump animations?"
)
```

### Good Pattern (After)
Neutral description followed by orchestrator logic.

```python
# Step 1: VQA describes exactly what it sees without bias
vqa_result = run_visual_qa_analysis(
    mode="question",
    game_screenshots=["screenshots/{task}/frame0001.png", "screenshots/{task}/frame0010.png"],
    question="Describe exactly what you see in each frame, specifically noting position, size, rotation, visible details of any character sprites, and any differences between frames."
)

# Step 2: Orchestrator decides pass/fail deterministically in Python
if "different frame" in vqa_result.lower() or "different sprite" in vqa_result.lower():
    verdict = "pass"
else:
    verdict = "fail"
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
