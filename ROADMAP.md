# Godogen Roadmap

This document tracks the evolution of godogen beyond defect fixes. Defects get fixed
in PRs and burned to zero. Features and architectural improvements live here, get
prioritized against each other, and graduate into Jules prompts when their time comes.

## In flight

Currently being implemented by Jules.

- **Tiered model routing for forked sub-agents** (prompt 3). Routes Visual QA fork
  and Godot API lookup fork to Gemini Flash via a `MODEL_CONFIG` dict at the top of
  the orchestrator. Main orchestrator stays on Pro preview. Note: the decomposer
  fork mentioned in the original prompt was dropped after discovering the decomposer
  is not actually a forked sub-agent in the current architecture (see Considered
  and Rejected).

- **Stage gate decoupling for sub-agents** (prompt A from latest cleanup batch).
  Refactor `process_function_calls` to accept an `enforce_stage_gates` parameter,
  defaulted True for the main orchestrator and explicitly False when called from
  forked sub-agents. Prevents future bugs where stage gates inadvertently apply to
  sub-agent contexts that have no meaningful "stage."

- **Stronger pipeline resumability** (prompt B from latest cleanup batch). Adds a
  `.godogen_state/stage_history.jsonl` log that records stage entries and
  completions independently of artifact files. Resumability checks now require both
  the artifact to exist AND the stage history to show prior completion, preventing
  the front-running edge case where an artifact appears out of order.

- **Replace xAI Grok with Imagen 4 and Veo 3.1 Lite**. Surgical swap in
  `asset_gen.py` to remove the xAI dependency entirely. Image generation moves to
  `imagen-4.0-generate-001`, video generation moves to `veo-3.1-lite-generate-preview`.
  Includes a critical caveat to *not* use Veo's `reference_images` parameter due to
  an unresolved Python SDK bug (googleapis/python-genai#1988); use the simpler
  `image` parameter instead.

---

## Feature backlog

These are capabilities godogen should have but doesn't yet. Roughly ordered by
leverage, but reorder freely as priorities shift.

### Tier 1: makes godogen feel like a creative tool, not a one-shot generator

- **Amend mode for iterative refinement.** Add an `--amend "list of changes"` flag
  that lets you point godogen at an existing project and request additions or fixes.
  The orchestrator treats existing artifacts as ground truth and only runs
  task-execution on the new items. This is the single most impactful feature for
  making godogen feel like a creative tool. Effort: 1-2 days. Without this, every
  iteration is a from-scratch regeneration, which is expensive and loses prior work.

- **Asset pack support.** Add a skill file (`asset-pack.md`) that teaches the
  orchestrator to detect when a directory of pre-made GLB or PNG assets is provided,
  prefer those assets over generation, and place them via `load() + instantiate()`
  with explicit transforms. Enables the Quaternius / Kenney / itch.io asset pack
  workflow and dramatically improves output quality on 3D scenes by skipping the
  weak Tripo3D generation step entirely. Effort: 1 day. Pairs naturally with
  amend mode.

- **House rules / project preamble.** A `HOUSE_RULES.md` file in the project
  directory that gets prepended to every orchestrator prompt as default behavior.
  Lets the user customize godogen's behavior per-project without editing skill
  files. Use cases: "always take multi-angle screenshots after major changes",
  "prefer cozy warm lighting", "use the assets in /assets/quaternius before
  generating new ones", "the player character is always controllable with WASD".
  Effort: half a day. Small change with outsized usability impact.

### Tier 2: improves reliability of what godogen already does

- **Multi-angle verification by default.** Currently visual QA captures from one
  camera angle per task. Add a "verify from multiple angles" mode that takes
  screenshots from N camera positions and runs VQA on all of them. Catches the
  "looks fine from this angle but clipping from that angle" failure mode that's
  endemic to 3D scenes. Costs more VQA calls (mitigated by Flash routing) but
  is the difference between trustworthy and wishful verification. Effort: 1-2 days.

- **Subjective verification via question mode.** The visual QA system already
  supports free-form questions. Wire up the orchestrator to use this for
  subjective creative direction prompts like "make the tavern feel cozy" by
  automatically running screenshots through VQA with questions like "does this
  tavern feel cozy, and if not what would make it cozier?" Unlocks a class of
  creative prompts that no conventional game tooling can handle. Effort: 1 day.

- **NPC interaction patterns library.** A skill file (`interactions.md`) that
  documents common patterns: proximity-triggered animation, click-to-open
  container, key-locked door, lever-activated mechanism, AnimationPlayer state
  swapping. Includes example GDScript and .tscn snippets the agent can adapt.
  Effort: 1-2 days. Right now the agent has to figure out these patterns from
  scratch each time; a library makes interactivity reliable.

- **Programmatic verification harnesses.** SceneTree test scripts that exercise
  mechanics in code and assert expected state changes via stdout, complementing
  screenshot-based VQA. Catches failures that don't manifest visually: collision
  off by two pixels, score updating on wrong signal, animation triggering on
  wrong condition. Effort: 2-3 days. The verification surface beyond visual is
  currently a blind spot.

### Tier 3: long-term investment in quality

- **Cross-run memory and learning.** A persistent JSON or SQLite store keyed by
  game-type tags that accumulates "things that failed in past runs and how we
  fixed them," loaded into the system prompt at pipeline start. Turns godogen
  from a generator that's identical on run 100 as on run 1 into a tool that
  improves with use. Effort: 3-5 days, plus ongoing curation discipline. The
  hard part isn't the storage, it's deciding what's worth remembering.

- **Metrics instrumentation.** Per-run logging of token spend split by stage and
  model, wall-clock time per stage, tool-call count, retry count per task, and
  final human-judgment quality score. Dump to CSV. After 20 runs, you have data
  to answer "is godogen getting better or worse over time" and "what changes
  actually moved the needle." Effort: 1-2 days for instrumentation, value
  accumulates over the next 6 months of use. Currently you're flying blind.

### Tier 4: speculative / strategic

- **MCP server interface.** Refactor godogen to expose its pipeline stages as MCP
  tools so any MCP-compatible client (Claude Code, Claude Desktop, Cursor) can
  drive the orchestration loop. Would let users substitute their preferred LLM as
  the "brain" while godogen remains the capability layer. Effort: 1-2 weeks
  refactor. Tabled for now pending clarity on whether the cost picture actually
  works out (Claude Pro / Max quota economics may not favor this for heavy users).
  See conversation history for the analysis.

- **Local VQA offload.** Run a vision model (Qwen2.5-VL, LLaVA, Moondream2)
  locally on the user's GPU for visual QA stages, eliminating those API calls
  entirely. Effort: 1 weekend for proof of concept, more for quality validation.
  Less compelling now that VQA is routed to Flash (which is cheap), but still
  unlocks rate-limit headroom on long runs.

- **Generalization beyond Godot.** The orchestration architecture (single 1M
  context, forked sub-agents, file-based state, stage gates) is not Godot-specific.
  The skill files are where domain knowledge lives. Refactoring to separate
  "orchestrator core" from "skill packs" would let godogen target Unity, Bevy,
  web frameworks, or app projects with the same backbone. Effort: weeks of real
  work. Strategic question rather than tactical: depends on whether godogen is
  becoming its own project or remaining a tool used to accelerate other work.

---

## Considered and rejected

Decisions made about things *not* to do, captured here so future maintainers don't
re-litigate them.

- **Forking the decomposer to run on Flash.** Originally proposed as part of the
  tiered model selection PR. Rejected because: the decomposer runs once per
  pipeline so cost savings are negligible (cents per run), the main orchestrator
  benefits from having decomposition reasoning in its context for downstream task
  execution, and the cache stability benefit is marginal on top of PR #13's
  existing fixes. The Flash routing for Visual QA and Godot API lookup captures
  all the actual cost savings without the architectural complexity.

- **Merging with godot-mcp (Coding-Solo).** Considered as a way to leverage an
  existing Godot MCP server. Rejected because godot-mcp is architecturally a thin
  CLI wrapper that shells out to `godot --headless` for each operation, which is
  what godogen already does internally. Integration would add a Node.js process
  boundary and TypeScript dependency for capabilities godogen already has. The
  more compelling version of this idea (a true live-editor bridge for Godot like
  Coplay's unity-mcp) doesn't currently exist in the Godot ecosystem and would
  be a major project to build from scratch.

- **Replacing Tripo3D for image-to-3D conversion.** Tripo3D produces uneven
  results, but no clearly better alternative exists at the same price point and
  the asset-pack support (Tier 1) provides a much better path forward for
  high-quality 3D output: skip image-to-3D entirely and use professional asset
  packs. Tripo3D stays for users who don't have asset packs available.

---

## How to use this document

When you have an idea, write it down here first under the appropriate tier. Don't
queue work until you've decided where it sits relative to other items. When you're
ready to actually do something, promote it from the backlog to "in flight" by
writing a Jules prompt for it. When it ships, move it to "completed" with a brief
note about what landed.

Resist the temptation to keep everything in your head. Ideas evaporate; documents
persist.
