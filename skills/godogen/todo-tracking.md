# TODO Tracking

Active execution tracker for task-execution stage.

TODO.md is a file in the project root that serves as the agent's working memory for the task execution stage. It is created when the agent enters the task execution stage (the orchestrator's stage transition message will include the initial TODO.md content based on PLAN.md's task list).

The agent must read TODO.md at the start of every turn during task execution and write to it at the end of every turn that makes meaningful progress.

## Format

The format of TODO.md is a simple markdown checklist with the following structure:
- A top section called "Current task" that names the single task the agent is currently working on.
- A "Steps" subsection that lists the immediate next actions for that task as a checklist.
- A "Done" subsection that records steps already completed during the current task.
- A "Remaining tasks" section at the bottom that lists upcoming tasks from PLAN.md in order.

Example TODO.md content for an in-progress task:

```markdown
# TODO

## Current task
Implement chest interaction (risk task 1)

## Steps
- [ ] Verify chest.tscn loads without error
- [ ] Implement basic boolean toggle in interactable_chest.gd
- [ ] Write test/test_interaction.gd
- [ ] Run test and verify it passes
- [ ] Mark task complete in PLAN.md

## Done (this task)
- [x] Read interactable_chest.gd
- [x] Read scenes/chest.tscn

## Remaining tasks
1. Implement door interaction
2. Build main scene with pack assets
3. Place player and configure first-person camera
4. Configure lighting
5. Generate presentation video
```

## Agent Responsibilities

- **Start of each turn**: Read TODO.md and identify the current task and the next unchecked step. Focus the turn's work on that step.
- **End of each turn**: Update TODO.md to mark completed steps as done, add new steps if the work revealed additional substeps.
- **When task is complete**: Mark it complete in PLAN.md, remove it from the Remaining tasks list, and start a new Current task section for the next task.

## Rules

- **No multiple current tasks**: The agent must never have more than one item under "Current task."
- **Prevent scope creep**: If the agent finds itself wanting to work on something not listed under the current task or the current task's steps, that is a signal that scope creep is happening. The agent must either add the new work as an explicit step under the current task (if it is required to complete the current task) or defer it to a future task (if it is not required).
- **No refactoring after completion**: The rule from task-execution.md about not refactoring after verification passes still applies: discoveries during verification do not become new steps under the current task, they become potential future amendments.
- **Signal of no progress**: If the agent exits a turn without updating TODO.md, the next turn's read of TODO.md will reveal the same state as the previous turn, and the agent should treat that as a signal that the previous turn made no meaningful progress and needs to reconsider its approach.

## Resumability

TODO.md is recreated from PLAN.md at the start of each task execution stage entry. If the agent resumes a project via the resumability state machine, the orchestrator should preserve TODO.md from the previous run if it exists, allowing the agent to continue where it left off.
