# Asset Generator

Generate PNG images (Imagen 4) and GLB 3D models (Tripo3D) from text prompts. Both image and video generation are routed through Google's native Imagen 4 and Veo 3.1 Lite APIs.

## Models

| Model | Flag | Cost | Best for |
|-------|------|------|----------|
| `imagen-4.0-generate-001` | N/A (Default) | 2¢ | All image generation (textures, simple objects, backgrounds, characters, 3D refs) |

**When to use which:**
- **Imagen 4** handles all image generation tasks previously split between models.

## CLI Reference

Tools live at `.gemini/skills/tools/`. Run from the project root.

### Generate image (2 cents)

```bash
python3 .gemini/skills/tools/asset_gen.py image \
  --prompt "the full prompt" -o assets/img/car.png
```

`--aspect-ratio` (default `1:1`): supports `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`.
*Note: `--model` and `--size` flags are deprecated and ignored if provided.*

Typical combos:
- `--aspect-ratio 1:1` — reference images, character sprites, 3D refs, item kits
- `--aspect-ratio 16:9` — backgrounds, title screens

### Remove background

Read `.gemini/skills/rembg.md` for full guide: CLI, prompting strategy, troubleshooting, batch mode.

### Generate animated sprite (2¢ ref + 2¢/pose + 5¢/sec video)

Workflow: reference → pose frame → video → slice → loop trim → rembg.

**Step 1: Reference image (2¢ — Imagen 4)**

Neutral pose, solid BG — same color strategy as for rembg. Review carefully: this image anchors all subsequent videos.

```bash
python3 .gemini/skills/tools/asset_gen.py image \
  --prompt "knight in armor, neutral standing pose, facing right, solid dark-green background" \
  --aspect-ratio 1:1 -o assets/img/knight_ref.png
```

**Step 2: Pose frame (2¢ — Imagen 4)**

*Note: Imagen 4 text-to-image does not natively support an `image` parameter for image-to-image edits in this script, though you can still generate the desired pose with careful prompting.*

```bash
python3 .gemini/skills/tools/asset_gen.py image \
  --prompt "knight in armor, walking to the right, mid-stride pose, side view, solid dark-green background" \
  --aspect-ratio 1:1 -o assets/img/knight_walk_pose.png
```

**Step 3: Generate video (Veo 3.1 Lite)**

Feed the pose frame (not the reference) as the starting image. Prompt focuses on the motion, not appearance.

*Note regarding Veo:*
- **Slow Generation:** Veo 3.1 Lite can take 30 to 90 seconds (wall clock) per video generation, so the script polls until completion.
- **Duration Floor:** Veo strictly requires durations between 4 and 8 seconds. Even if you request 2s, the CLI will clamp your request to 4s to satisfy the API.
- **Reference Images:** Veo's Python SDK currently has a broken `reference_images` parameter (googleapis/python-genai #1988). Godogen correctly works around this by using the `image` parameter instead, which starts the video directly from the pose frame.

```bash
python3 .gemini/skills/tools/asset_gen.py video \
  --prompt "walking to the right, smooth walk cycle, solid dark-green background" \
  --image assets/img/knight_walk_pose.png \
  --duration 4 -o assets/video/knight_walk.mp4
```

`--duration` (>= 4 seconds), `--resolution` (deprecated, ignored by Veo)

**Step 4: Extract frames**

```bash
mkdir -p assets/video/knight_walk_frames
ffmpeg -i assets/video/knight_walk.mp4 -vsync 0 assets/video/knight_walk_frames/%04d.png
```

**Step 5: Loop trim (looping animations only)**

For walk/run/idle cycles, find the best loop point. Picks top similarity candidates, deduplicates nearby frames, then chooses the latest (longest clip). Uses 7-frame window to avoid half-cycle cuts, falls back to 1-frame, then whole clip. Skip for one-shot animations (attack, death, jump).

```bash
python3 .gemini/skills/tools/find_loop_frame.py assets/video/knight_walk_frames/
```

Output: `{"loop_frame": 54, "similarity": 0.9983, "window": 7, "total_frames": 73}`

`window: 0` means no good loop point — use the whole clip. Then delete frames after the loop point, or note the range for the next step.

**Step 6: Batch background removal** (see `rembg.md` for full guide)

```bash
python3 .gemini/skills/tools/rembg_matting.py \
  --batch assets/video/knight_walk_frames/ \
  -o assets/img/knight_walk/
```

**Step 7: Additional animations**

Repeat from step 2 for other poses. Each new animation costs 2¢ (pose) + video duration × 5¢.

### Convert image to GLB (40-50 cents)

```bash
python3 .gemini/skills/tools/asset_gen.py glb \
  --image assets/img/car.png -o assets/glb/car.glb
```

`--quality`: `default` (P1, 50¢) or `high` (v3.1 + HD textures, 40¢)

### Set budget

```bash
python3 .gemini/skills/tools/asset_gen.py set_budget 500
```

Sets the generation budget to 500 cents. All subsequent generations check remaining budget and reject if insufficient. CRITICAL: only call once at the start, and only when the user explicitly provides a budget.

### Output format

JSON to stdout: `{"ok": true, "path": "assets/img/car.png", "cost_cents": 7}`

On failure: `{"ok": false, "error": "...", "cost_cents": 0}`

Progress goes to stderr.

## Cost Table

| Operation | Options | Cost | Notes |
|-----------|---------|------|-------|
| Image | Any | 2 cents | Handled by Imagen 4 |
| GLB | default | 50 cents | P1 model, fast, game-optimized topology |
| GLB | high | 40 cents | v3.1, HD textures |
| Video | --duration N | 5¢ × N seconds | Veo 3.1 Lite (N clamped to 4-8s) |

A full 3D asset (Imagen image + GLB) costs 42 cents at high quality. A background is 2¢. A 4-second animation costs 24 cents (2¢ ref + 2¢ pose + 20¢ video).

## Image Resolution

Imagen 4 doesn't support the `size` parameter. Rely on `aspect-ratio`.

### Small sprites problem

Minimum generation resolution is 1K. A 1024px image downscaled to 64px or even 128px loses all fine detail and looks muddy. Mitigations:

1. **Avoid tiny display sizes.** Design game elements at 128px+ where possible. If a sprite must be small in-game, question whether it needs to be a generated image at all (a colored rectangle or simple shape drawn in code may read better at that size).
2. **Generate a kit image** — put multiple objects on one 1K image (e.g. 4 items in a 2x2 layout, each occupying ~512px) and crop the regions you need. More pixels per object = cleaner downscale.
3. **Prompt for bold, simple forms.** When the target display size is small, explicitly ask for: thick outlines, flat colors, minimal fine detail, exaggerated proportions. These survive downscaling; intricate textures don't.

## What to Generate — Cheatsheet

For any asset needing transparency, read `.gemini/skills/rembg.md` first — covers BG color strategy, CLI, and troubleshooting.

### Background / large scenic image (2c)

Title screens, sky panoramas, parallax layers, environmental art. Best place for art direction language.

```
{description in the art style}. {composition instructions}.
```
`image --prompt "..." --aspect-ratio 16:9 -o path.png`

No post-processing — use as-is.

### Texture (2c)

Tileable surfaces: ground, walls, floors, UI panels.

```
{name}, {description}. Top-down view, uniform lighting, no shadows, seamless tileable texture, suitable for game engine tiling, clean edges.
```
`image --prompt "..." -o path.png`

No background removal — the entire image IS the texture.

### Single object / sprite

Props, items, icons, characters, enemies, NPCs:
```
{name}, {description}. Centered on a solid {bg_color} background.
```
`image --prompt "..." -o path.png`

*(Note: Imagen 4 does not support passing a reference image for variants via the CLI currently.)*

### Item kit (2c for 4 items)

Generate multiple objects in one image, then slice. Cheaper than generating individually.

```
{item1}, {item2}, {item3}, {item4}. 2x2 grid layout, each item centered in its cell, solid {bg_color} background. {art style}.
```
`image --prompt "..." -o path_grid.png`

Slice into individual PNGs:
```bash
python3 .gemini/skills/tools/grid_slice.py path_grid.png \
  -o assets/img/items/ --grid 2x2 --names "sword,shield,potion,helm"
```

Then rembg each item if transparency is needed. Supports any grid: `2x2`, `3x3`, `2x4`, etc.

### 3D model reference (2c) + GLB (40-50c)

Clean composition and precise prompt following are critical for 3D conversion.

```
3D model reference of {name}. {description}. 3/4 front elevated camera angle, solid white background, soft diffused studio lighting, matte material finish, single centered subject, no shadows on background. Any windows or glass should be solid tinted (opaque).
```
`image --prompt "..." -o path.png`

Then: `glb --image ... -o ...` — do NOT remove the background; Tripo3D needs the solid white bg for clean separation.

Key: 3/4 front elevated angle, solid white/gray bg, matte finish (no reflections), opaque glass, single centered subject.

### Animated sprite

Full workflow (ref → pose → video → frames → loop trim → rembg) is in CLI Reference above. Prompt templates:

**Reference:** `{name}, {description}. Neutral standing pose, facing right, centered on a solid {bg_color} background. Clean silhouette.`

**Pose (per action):** `{name}, {description}, {action pose description}, side view, solid {bg_color} background.`

**Video (per action):** `{action}, smooth animation. Solid {bg_color} background.`

## Visual Pitfalls

Image generators and vision validators have poor spatial understanding. These issues are invisible to the agent but degrade quality significantly. Verify carefully.

### Direction and orientation

Generators cannot reliably distinguish left vs right facing, or produce correct rotations. Prompting for "NE facing" vs "NW facing" often produces identical output.

**Solution:** Generate one direction only (sprites are typically left-facing), flip horizontally for the opposite direction (`sprite.flip_h = true`). Use visual-qa question mode to verify orientation when it matters — don't trust the generator got it right.

### Video size consistency

When mixing image-generated assets (1024px) with video-extracted frames (~720px), resize everything to the smallest source size. Downscale the 1024px images to match video frame resolution — upscaling is rarely needed. Do this before background removal.

Use ImageMagick:
```bash
magick identify input.png                                      # check size
magick input.png -resize 720x720 -filter Lanczos output.png   # resize
magick input.png -flop output.png                              # horizontal flip
```

### Animation playback

Video-extracted animations look choppy when played back at the wrong frame rate. Source videos are typically 24fps — set frame duration to `1.0/24 = 0.042s`. Don't reset the animation frame counter between movement tiles; let it run continuously across boundaries.

## Tips

- Generate multiple images in parallel via multiple Bash calls in one message.
- Always review generated PNGs before GLB conversion — read each image and check: centered? complete? clean background? Regenerate bad ones first; a bad image wastes 30+ cents on GLB.
- Convert approved images to GLBs in parallel.
