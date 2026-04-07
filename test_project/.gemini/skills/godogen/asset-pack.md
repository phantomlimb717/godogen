# Asset Pack Support

When the user has a directory of GLB files in their project at `assets/packs/`, the orchestrator should detect it, list its contents, and prefer loading from it over generating new 3D assets via Tripo3D.

Pre-made packs are professionally modeled, share consistent scale and style across the entire pack, and use efficient texture atlases. This workflow bypasses the Tripo3D bottleneck entirely.

## Protocol

At the start of the asset planning stage, check for the existence of `assets/packs/` in the project directory. If the directory exists, enumerate all GLB files within it recursively (packs may be organized into subdirectories like `assets/packs/quaternius_fantasy/`) and treat the resulting inventory as the primary source for 3D models.

The agent must follow a strict six-step asset matching and substitution protocol for every 3D asset requested by the plan.

### Step 1: Exact Match

Scan the pack inventory for an exact name match, case-insensitive, ignoring file extensions and word separators like underscores or hyphens. "Barrel" matches `Barrel.glb`, `barrel.glb`, `wooden_barrel.glb`.

If an exact match is found, use it directly and the protocol ends here.

### Step 2: Semantic Neighbor Identification

If no exact match exists, scan the inventory for semantic neighbors: assets in the same broad category that could plausibly serve a similar function. Examples of valid semantic pairs:
- table for desk
- chair for stool
- sword for blade
- cup for mug
- candle for torch
- crate for box
- lantern for lamp

List all candidates rather than picking the first one.

### Step 3: Three-Criteria Substitution Check

For each candidate, evaluate three questions. You must answer **YES** to all three for the substitution to proceed:

1. **Meaning:** Would the substitution preserve the meaning of the scene as described in the prompt?
   - *Example:* A "wizard's potion table covered in glowing flasks" cannot be substituted with a plain table because the substitution would lose the meaning.
   - *Example:* A "wooden table in a tavern" can be substituted with any reasonable table from the pack because the meaning is preserved.
2. **Gameplay Function:** Would the substitution preserve the gameplay function?
   - *Example:* A "treasure chest the player can open and loot" cannot be substituted with a non-interactive crate because the player will try to interact with it and find broken affordances.
   - *Example:* A purely decorative table or chair has no gameplay function and is freely substitutable.
3. **Visual Acceptability:** Would a casual viewer find the substitution visually acceptable?
   - *Example:* A throne substituted with a stool is glaringly wrong.
   - *Example:* A dining chair substituted with a slightly different dining chair is invisible.
   - *Tip:* Imagine showing the resulting scene to someone who didn't see the original prompt and ask whether they would notice anything off.

### Step 4: Substitution with Documentation

If a candidate passes all three criteria, use it and document the substitution in `ASSETS.md` by adding a note to the asset row in this format:

`Substituted from pack: Table.glb (no exact desk in pack)`

The substituted asset is used in the Godot scene with the same loading pattern as exact matches.

### Step 5: Generation Fallback

If no candidate passes all three criteria, fall back to Tripo3D generation for this specific asset only.

The generation reason must be documented in `ASSETS.md` in this format:

`Generated via Tripo3D: no suitable match in pack for "wizard potion table"`

The fallback uses the existing Imagen 4 + Tripo3D pipeline unchanged.

### Step 6: Pack Coverage Tracking

Track the substitution rate across the whole scene as you process the plan. After all 3D assets have been resolved (whether by exact match, substitution, or generation), calculate the percentages.

If **more than 50%** of the requested 3D assets required substitution or generation rather than exact matches, append a warning to `ASSETS.md` in this format:

`Pack coverage warning: only X of Y 3D assets were exact matches. Consider expanding the asset pack or amending the prompt to better match available assets.`

This warning is informational; it does not block the run.

## Explicit Rules

- This protocol applies to **every** 3D asset the plan requests.
- You must **not** silently substitute or silently generate. Every decision must be documented in `ASSETS.md` so the user can audit the choices after the run completes.
- Pack files are **read-only inputs**. Never modify, overwrite, or delete files in `assets/packs/`. Generated assets continue to live in `assets/img/` and `assets/glb/` as they do today; pack assets stay in their original directories.
- You must **NOT** attempt to extract individual meshes from a single combined GLB file. If a pack ships as one giant scene file containing multiple props, treat it as a single asset and place it as a whole. Splitting combined files is out of scope.

## GDScript Loading Pattern

Use the following GDScript pattern to load and instantiate pack assets:

```gdscript
var barrel_scene = load("res://assets/packs/quaternius_fantasy/Barrel.glb")
var barrel_instance = barrel_scene.instantiate()
add_child(barrel_instance)
barrel_instance.position = Vector3(3.5, 0, -2.1)
barrel_instance.rotation.y = deg_to_rad(45)
```

## Visual QA Verification

You must still use Visual QA to verify pack asset placement after each scene change. The verification question should focus on **spatial coherence** rather than asset quality:
- Is the barrel in a sensible location?
- Does the chest face the right direction?
- Are the props at consistent scale relative to each other and to the player character?

Pack assets being professionally made means the quality of individual assets is not in question, but the placement still needs verification because that's your responsibility.
