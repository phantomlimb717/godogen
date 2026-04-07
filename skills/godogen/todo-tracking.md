# TODO Tracking

Active execution tracker for the task-execution stage.

TODO.md is a file in the project root that serves as your working memory for the task execution stage. It is created when you enter the task execution stage. The orchestrator's stage transition message will include the initial TODO.md content based on PLAN.md's task list.

You must read `TODO.md` at the start of every turn during task execution and write to it at the end of every turn that makes meaningful progress.

## Format

The format of `TODO.md` is a simple markdown checklist with the following structure:
- **Current task**: The single task you are currently working on.
- **Steps**: The immediate next actions for that task as a checklist.
- **Done**: Steps already completed during the current task.
- **Remaining tasks**: Upcoming tasks from PLAN.md in order.

### Example TODO.md

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

## Responsibilities

1. **Start of each turn**: Read `TODO.md` and identify the current task and the next unchecked step. Focus the turn's work strictly on that step.
2. **End of each turn**: Update `TODO.md` to mark completed steps as done in the `Done (this task)` section, and add new steps to the `Steps` section if the work revealed additional substeps.
3. **Task completion**: If the entire current task is complete:
   - Mark it complete in `PLAN.md`.
   - Remove it from the `Remaining tasks` list.
   - Start a new `Current task` section for the next task.
   - Clear the `Steps` and `Done` sections for the new task.
4. **Single Task Rule**: You must never have more than one item under "Current task." If you find yourself wanting to work on something not listed under the current task or its steps, that is a signal of scope creep. You must either:
   - Add the new work as an explicit step under the current task (if it is required to complete it).
   - Defer it to a future task in `PLAN.md` (if it is not required).
5. **No Refactoring**: Discoveries during verification do not become new steps under the current task if verification passes. They become potential future amendments.
6. **Stuck Detection**: If you exit a turn without updating `TODO.md`, the next turn's read will reveal the same state. Treat that as a signal that the previous turn made no meaningful progress and you need to reconsider your approach.

## Resumability

`TODO.md` is recreated from `PLAN.md` at the start of each task execution stage entry. If you resume a project via the resumability state machine, the orchestrator will preserve `TODO.md` from the previous run if it exists, allowing you to continue exactly where you left off.
