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

    gitignore_path = os.path.join(target, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w") as f:
            f.write(".gemini\nGEMINI.md\nassets\nscreenshots\n.vqa.log\n.godot\n*.import\n")
        print("Created .gitignore")

    house_rules_path = os.path.join(target, "HOUSE_RULES.md")
    if not os.path.exists(house_rules_path):
        with open(house_rules_path, "w") as f:
            f.write("""# House Rules

These are project-wide preferences that the godogen agent will follow for every
generation and amendment in this project. Add your standing instructions below.
The file is read at the start of each run; changes take effect on the next run.

Examples of useful house rules:

- Always take screenshots from multiple camera angles after major scene changes,
  and verify each angle through visual QA before marking a task complete.
- Prefer warm, cozy lighting (low color temperature, soft shadows) for all
  interior scenes unless the prompt explicitly requests otherwise.
- When 3D assets are needed and the directory `assets/quaternius/` exists, prefer
  loading from that directory before generating new assets via Tripo3D.
- The player character is always named "Pip" and always uses the WASD control
  scheme unless the user specifies otherwise.

Delete the examples above and add your own rules below this line.

---

""")
        print("Created HOUSE_RULES.md template")

    try:
        subprocess.run(["git", "init", "-q"], cwd=target, stderr=subprocess.DEVNULL, check=False)
    except FileNotFoundError:
        # git not installed or not in PATH, skip silently as in the original bash script
        pass

    num_skills = len([name for name in os.listdir(skills_target) if os.path.isdir(os.path.join(skills_target, name))])
    print(f"Done. skills: {num_skills}")

if __name__ == "__main__":
    main()
