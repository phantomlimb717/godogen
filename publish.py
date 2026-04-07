import sys
import os
import shutil
import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser(description="Publish godogen skills into a target project directory.")
    parser.add_argument("target_dir", help="Target directory")
    parser.add_argument("--force", action="store_true", help="Delete existing target contents before publishing")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.abspath(__file__))
    target = os.path.abspath(args.target_dir)

    if args.force and os.path.exists(target):
        print(f"Force: cleaning {target}")
        shutil.rmtree(target, ignore_errors=True)

    if not os.path.exists(target):
        os.makedirs(target)

    print(f"Publishing to: {target}")

    skills_target = os.path.join(target, ".gemini", "skills")
    os.makedirs(skills_target, exist_ok=True)

    skills_source = os.path.join(repo_root, "skills")

    def ignore_patterns(path, names):
        return [n for n in names if n in ['doc_source', '__pycache__']]

    for item in os.listdir(skills_source):
        s = os.path.join(skills_source, item)
        d = os.path.join(skills_target, item)
        if os.path.isdir(s):
            if item in ['doc_source', '__pycache__']:
                continue
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(s, d, ignore=ignore_patterns)
        else:
            shutil.copy2(s, d)

    shutil.copy2(os.path.join(repo_root, "game.md"), os.path.join(target, "GEMINI.md"))
    print("Created GEMINI.md")

    shutil.copy2(os.path.join(repo_root, "gemini_orchestrator.py"), os.path.join(target, "gemini_orchestrator.py"))
    print("Copied gemini_orchestrator.py")

    packs_dir = os.path.join(target, "assets", "packs")
    os.makedirs(packs_dir, exist_ok=True)
    with open(os.path.join(packs_dir, ".gitkeep"), "w") as f:
        pass

    readme_content = """# Asset Packs

Place pre-made GLB asset packs in this directory to have godogen use them
instead of generating 3D assets via Tripo3D. Each pack should live in its own
subdirectory, e.g.:

```
assets/packs/quaternius_fantasy/
  Barrel.glb
  Chest.glb
  Table.glb
  ...
assets/packs/kenney_medieval/
  Sword.glb
  Shield.glb
  ...
```

Godogen will detect packs automatically at the start of asset planning. Assets
that exactly match a pack file will be used directly. Assets without an exact
match may be substituted from semantic neighbors (e.g. a "table" for a "desk")
or generated via Tripo3D as a fallback. All decisions are logged in ASSETS.md.

Recommended sources for CC0 GLB packs:
- Quaternius (https://quaternius.com)
- Kenney (https://kenney.nl)

Pack files are treated as read-only by godogen. Do not edit them in place; if
you need a modified version, edit a copy outside the packs directory.
"""
    with open(os.path.join(packs_dir, "README.md"), "w") as f:
        f.write(readme_content)
    print("Created assets/packs directory and README.md")

    gitignore_path = os.path.join(target, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w") as f:
            f.write(".gemini\nGEMINI.md\nassets\nscreenshots\n.vqa.log\n.godot\n*.import\n")
        print("Created .gitignore")

    try:
        subprocess.run(["git", "init", "-q"], cwd=target, stderr=subprocess.DEVNULL, check=False)
    except FileNotFoundError:
        # git not installed or not in PATH, skip silently as in the original bash script
        pass

    num_skills = len([name for name in os.listdir(skills_target) if os.path.isdir(os.path.join(skills_target, name))])
    print(f"Done. skills: {num_skills}")

if __name__ == "__main__":
    main()
