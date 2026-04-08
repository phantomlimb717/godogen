# Amend Mode

You are currently in **Amend Mode**, meaning you are iterating on an already existing, working Godogen project. Your primary objective is to execute an incremental change based on the user's amendment request without regenerating the entire project or destroying what is already there.

The user's amendment request describes what they want added or fixed.
If the amendment request is ambiguous, make reasonable assumptions and document them in the amendment task description, rather than asking the user for clarification (the orchestrator does not currently support interactive clarification).

## Context Reading
You must begin by understanding the current state of the project. Read the following ground-truth files:
1. `PLAN.md` to understand the current task list and project state.
2. `STRUCTURE.md` to understand the project architecture and scene layout.
3. `ASSETS.md` to understand what assets already exist.

## Task Decomposition
Decompose the amendment request into one or more new tasks.
- Follow the same risk-task identification rules as the main decomposer: collision-based mechanics get isolated, observable state transitions get isolated, multi-direction sprite animations get isolated, etc.
- Append these new tasks to `PLAN.md` under a new `# Amendments` section (or append to it if it already exists).
- Use a clear timestamp header for the current amendment (e.g., `## Amendment: YYYY-MM-DD HH:MM:SS`).

## Execution Constraints
- Execute the new tasks using the same task-execution workflow as the main pipeline, including Visual QA verification.
- Prefer reusing existing assets, scenes, and scripts when possible. Only generate new assets if the amendment genuinely requires assets that don't exist in the project. The goal of amend mode is incremental refinement, not regeneration.
- **DO NOT** regenerate or re-verify anything that already works.
- **DO NOT** touch tasks that were completed in earlier runs or earlier amendments.
