import os
import sys
import shutil
import subprocess
import argparse
import platform
import glob

def get_godot_cmd():
    plat = platform.system()
    if plat == "Windows":
        return ["godot", "--rendering-method", "forward_plus"], True, None
    elif plat == "Darwin":
        return ["godot", "--rendering-method", "forward_plus"], True, None
    else: # Linux
        # Check for X11 sockets to determine if GPU is available
        for sock in glob.glob('/tmp/.X11-unix/X*'):
            d = ":" + sock.split('X')[-1]
            try:
                env = os.environ.copy()
                env['DISPLAY'] = d
                # Check with glxinfo if there's a GPU
                res = subprocess.run(['glxinfo'], env=env, capture_output=True, text=True, timeout=2)
                if 'opengl renderer' in res.stdout.lower() and 'nvidia' in res.stdout.lower():
                    return ["godot", "--rendering-method", "forward_plus"], True, d
                elif 'opengl renderer' in res.stdout.lower():
                    return ["godot", "--rendering-method", "forward_plus"], True, d
            except Exception:
                pass

        # Fallback to software rasterizer via xvfb if no GPU found
        return ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24", "godot", "--rendering-driver", "vulkan"], False, None

def main():
    parser = argparse.ArgumentParser(description="Capture screenshots or video from a Godot project.")
    parser.add_argument("--task", required=True, help="Task folder name (e.g., task_01_terrain)")
    parser.add_argument("--script", required=True, help="GDScript to run for capture")
    parser.add_argument("--fps", type=int, default=10, help="Frames per second")
    parser.add_argument("--frames", type=int, required=True, help="Number of frames to capture (--quit-after)")
    parser.add_argument("--video", action="store_true", help="Capture video instead of screenshots")
    args = parser.parse_args()

    cmd_prefix, gpu_available, display = get_godot_cmd()

    if args.video and not gpu_available:
        print("No GPU available — skipping video capture")
        return

    out_dir = "screenshots/presentation" if args.video else f"screenshots/{args.task}"
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    os.makedirs("screenshots", exist_ok=True)
    with open("screenshots/.gdignore", "w") as f:
        f.write("")

    godot_cmd = cmd_prefix + [
        "--write-movie", f"{out_dir}/output.avi" if args.video else f"{out_dir}/frame.png",
        "--fixed-fps", str(args.fps),
        "--quit-after", str(args.frames),
        "--script", args.script
    ]

    print(f"Running: {' '.join(godot_cmd)}")

    timeout = 60 if args.video else 30
    env = os.environ.copy()
    if display:
        env['DISPLAY'] = display

    output_buffer = []

    try:
        # Run Godot, capturing stdout and stderr into a single pipe
        # We use capture_output=True and timeout properly enforced by subprocess.run
        res = subprocess.run(
            godot_cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False
        )

        # Tee the output
        if res.stdout:
            sys.stdout.write(res.stdout)
            output_buffer = res.stdout.splitlines()

    except subprocess.TimeoutExpired as e:
        print("Godot run timed out (expected if it doesn't quit cleanly)")
        if e.stdout:
            sys.stdout.write(e.stdout)
            if isinstance(e.stdout, str):
                output_buffer = e.stdout.splitlines()
            else:
                output_buffer = e.stdout.decode('utf-8', errors='replace').splitlines()
    except Exception as e:
        print(f"Failed to run Godot: {e}")

    error_prefixes = ["ERROR:", "SCRIPT ERROR:", "Parse Error:"]
    found_errors = []

    # Scan the buffer for errors
    if output_buffer:
        for i, line in enumerate(output_buffer):
            line_stripped = line.strip()
            if any(line_stripped.startswith(prefix) for prefix in error_prefixes):
                # Grab this line and the next few lines to get context (like "at: ...")
                error_context = [line_stripped]

                # Check up to 2 subsequent lines for "at:" context
                for j in range(1, 3):
                    if i + j < len(output_buffer):
                        next_line = output_buffer[i + j].strip()
                        if next_line.startswith("at:") or next_line.startswith("ERROR: Failed to load script"):
                            error_context.append(next_line)
                        else:
                            break

                found_errors.append("\n".join(error_context))

    if found_errors:
        print("\n--- CAPTURE FAILED: GODOT ERRORS DETECTED ---", file=sys.stderr)
        for err in found_errors:
            print(f"{err}", file=sys.stderr)
        sys.exit(1)

    if args.video:
        mp4_path = f"{out_dir}/gameplay.mp4"
        avi_path = f"{out_dir}/output.avi"
        if not os.path.exists(avi_path):
            print("Video capture failed: output.avi not found")
            return

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", avi_path,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28", "-preset", "slow",
            "-vf", "scale='min(1280,iw)':-2",
            "-movflags", "+faststart",
            mp4_path
        ]
        print(f"Converting to MP4: {' '.join(ffmpeg_cmd)}")
        try:
            subprocess.run(ffmpeg_cmd, check=True)
            print(f"Video saved to {mp4_path}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to convert video: {e}")

if __name__ == "__main__":
    main()
