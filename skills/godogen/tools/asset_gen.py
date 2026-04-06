#!/usr/bin/env python3
"""Asset Generator CLI - creates images (Gemini / xAI Grok) and GLBs (Tripo3D).

Subcommands:
  image   Generate a PNG from a prompt (Gemini 5-15¢ or Grok 2¢)
  video   Generate MP4 video from prompt + reference image (5¢/sec, Grok)
  glb     Convert a PNG to a GLB 3D model via Tripo3D (30-60¢)

Output: JSON to stdout. Progress to stderr.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from tripo3d import MODEL_P1, MODEL_V31, image_to_glb

TOOLS_DIR = Path(__file__).parent
BUDGET_FILE = Path("assets/budget.json")

VIDEO_COST_PER_SEC = 5  # cents


def _load_budget():
    if not BUDGET_FILE.exists():
        return None
    return json.loads(BUDGET_FILE.read_text())


def _spent_total(budget):
    return sum(v for entry in budget.get("log", []) for v in entry.values())


def check_budget(cost_cents: int):
    """Check remaining budget. Exit with error JSON if insufficient."""
    budget = _load_budget()
    if budget is None:
        return
    spent = _spent_total(budget)
    remaining = budget.get("budget_cents", 0) - spent
    if cost_cents > remaining:
        result_json(False, error=f"Budget exceeded: need {cost_cents}¢ but only {remaining}¢ remaining ({spent}¢ of {budget['budget_cents']}¢ spent)")
        sys.exit(1)


def record_spend(cost_cents: int, service: str):
    """Append a generation record to the budget log."""
    budget = _load_budget()
    if budget is None:
        return
    budget.setdefault("log", []).append({service: cost_cents})
    BUDGET_FILE.write_text(json.dumps(budget, indent=2) + "\n")

QUALITY_PRESETS = {
    "default": {
        "model_version": MODEL_P1,
        "texture_quality": "standard",
        "cost_cents": 50,
    },
    "high": {
        "model_version": MODEL_V31,
        "texture_quality": "detailed",
        "cost_cents": 40,
    },
}


def result_json(ok: bool, path: str | None = None, cost_cents: int = 0, error: str | None = None):
    d = {"ok": ok, "cost_cents": cost_cents}
    if path:
        d["path"] = path
    if error:
        d["error"] = error
    print(json.dumps(d))


# --- Image backends ---

IMAGEN_MODEL = "imagen-4.0-generate-001"
IMAGEN_COST = 2  # Flat cost for image gen
IMAGEN_ASPECT_RATIOS = [
    "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"
]

ALL_SIZES = ["512", "1K", "2K", "4K"]
ALL_ASPECT_RATIOS = IMAGEN_ASPECT_RATIOS


def _generate_imagen(args, output: Path, cost: int):
    try:
        client = genai.Client()

        response = client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=args.prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=args.aspect_ratio,
                output_mime_type='image/png',
            ),
        )

        if not response.generated_images:
            result_json(False, error="No image returned")
            sys.exit(1)

        response.generated_images[0].image.save(str(output))

    except Exception as e:
        result_json(False, error=str(e))
        sys.exit(1)

    print(f"Saved: {output}", file=sys.stderr)
    record_spend(cost, "imagen")
    result_json(True, path=str(output), cost_cents=cost)


def cmd_image(args):
    if "--size" in sys.argv:
        print("Warning: --size is ignored. Imagen 4 does not support the size parameter.", file=sys.stderr)

    cost = IMAGEN_COST

    check_budget(cost)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    label = f"imagen {args.aspect_ratio}"
    if args.image:
        print("Warning: image-to-image reference is ignored by Imagen 4 text-to-image generation.", file=sys.stderr)
        label += " (image ignored)"

    print(f"Generating image ({label})...", file=sys.stderr)
    _generate_imagen(args, output, cost)


def cmd_video(args):
    # Enforce minimum duration of 4 for Veo
    duration = args.duration
    if duration < 4:
        print(f"Warning: Duration {duration}s is below Veo's minimum. Clamping to 4s.", file=sys.stderr)
        duration = 4
    elif duration > 8:
        print(f"Warning: Duration {duration}s is above Veo's maximum. Clamping to 8s.", file=sys.stderr)
        duration = 8

    cost = duration * VIDEO_COST_PER_SEC
    check_budget(cost)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    image_path = Path(args.image)
    if not image_path.exists():
        result_json(False, error=f"Reference image not found: {image_path}")
        sys.exit(1)

    print(f"Generating {duration}s video with veo-3.1-lite-generate-preview...", file=sys.stderr)

    try:
        client = genai.Client()
        reference_image = Image.open(image_path) if image_path else None

        # Determine aspect ratio for Veo (only 16:9 and 9:16 supported)
        aspect_ratio = "16:9"
        if reference_image:
            w, h = reference_image.size
            if h > w:
                aspect_ratio = "9:16"

        operation = client.models.generate_videos(
            model='veo-3.1-lite-generate-preview',
            prompt=args.prompt,
            image=reference_image,
            config=types.GenerateVideosConfig(
                person_generation='allow_adult',
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
                duration_seconds=duration,
            ),
        )

        print("  Waiting for video generation to complete...", file=sys.stderr)
        while not operation.done:
            time.sleep(15)
            operation = client.operations.get(operation)

        generated_video = operation.response.generated_videos[0]
        client.files.download(file=generated_video.video)
        generated_video.video.save(str(output))

    except Exception as e:
        result_json(False, error=str(e))
        sys.exit(1)

    print(f"Saved: {output}", file=sys.stderr)
    record_spend(cost, "veo-video")
    result_json(True, path=str(output), cost_cents=cost)


def cmd_glb(args):
    image_path = Path(args.image)
    if not image_path.exists():
        result_json(False, error=f"Image not found: {image_path}")
        sys.exit(1)

    preset = QUALITY_PRESETS.get(args.quality, QUALITY_PRESETS["default"])
    check_budget(preset["cost_cents"])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Converting to GLB (quality={args.quality})...", file=sys.stderr)

    try:
        image_to_glb(
            image_path,
            output,
            model_version=preset["model_version"],
            texture_quality=preset["texture_quality"],
        )
    except Exception as e:
        result_json(False, error=str(e))
        sys.exit(1)

    print(f"Saved: {output}", file=sys.stderr)
    record_spend(preset["cost_cents"], "tripo3d")
    result_json(True, path=str(output), cost_cents=preset["cost_cents"])


def cmd_set_budget(args):
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    budget = {"budget_cents": args.cents, "log": []}
    if BUDGET_FILE.exists():
        old = json.loads(BUDGET_FILE.read_text())
        budget["log"] = old.get("log", [])
    BUDGET_FILE.write_text(json.dumps(budget, indent=2) + "\n")
    spent = _spent_total(budget)
    print(json.dumps({"ok": True, "budget_cents": args.cents, "spent_cents": spent, "remaining_cents": args.cents - spent}))


def main():
    parser = argparse.ArgumentParser(description="Asset Generator — images (Imagen 4) and GLBs (Tripo3D)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_img = sub.add_parser("image", help="Generate a PNG image (Imagen 4, 2¢)")
    p_img.add_argument("--prompt", required=True, help="Full image generation prompt")
    p_img.add_argument("--model", choices=["gemini", "grok", "imagen"], default="imagen",
                       help="Deprecated. All image generation uses Imagen 4.")
    p_img.add_argument("--size", choices=ALL_SIZES, default="1K",
                       help="Deprecated. Ignored by Imagen 4.")
    p_img.add_argument("--aspect-ratio", choices=ALL_ASPECT_RATIOS, default="1:1",
                       help="Aspect ratio. Default: 1:1")
    p_img.add_argument("--image", default=None, help="Reference image (ignored by Imagen 4 text-to-image)")
    p_img.add_argument("-o", "--output", required=True, help="Output PNG path")
    p_img.set_defaults(func=cmd_image)

    p_vid = sub.add_parser("video", help="Generate MP4 video from prompt + reference image (Veo 3.1 Lite, 5¢/sec)")
    p_vid.add_argument("--prompt", required=True, help="Video generation prompt")
    p_vid.add_argument("--model", choices=["grok", "gemini", "veo"], default="veo",
                       help="Deprecated. All video generation uses Veo 3.1 Lite.")
    p_vid.add_argument("--image", required=True, help="Reference image path (starting frame)")
    p_vid.add_argument("--duration", type=int, required=True, help="Duration in seconds (>= 4)")
    p_vid.add_argument("--resolution", choices=["480p", "720p", "1080p", "4k"], default="720p",
                       help="Video resolution (deprecated/ignored by Veo). Default: 720p")
    p_vid.add_argument("-o", "--output", required=True, help="Output MP4 path")
    p_vid.set_defaults(func=cmd_video)

    p_glb = sub.add_parser("glb", help="Convert PNG to GLB 3D model (30-60 cents)")
    p_glb.add_argument("--image", required=True, help="Input PNG path")
    p_glb.add_argument("--quality", default="default", choices=list(QUALITY_PRESETS.keys()), help="Quality preset")
    p_glb.add_argument("-o", "--output", required=True, help="Output GLB path")
    p_glb.set_defaults(func=cmd_glb)

    p_budget = sub.add_parser("set_budget", help="Set the asset generation budget in cents")
    p_budget.add_argument("cents", type=int, help="Budget in cents")
    p_budget.set_defaults(func=cmd_set_budget)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
