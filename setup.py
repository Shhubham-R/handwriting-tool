#!/usr/bin/env python3
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
REPO_DIR = MODELS_DIR / "handwriting-synthesis"
REPO_URL = "https://github.com/sjvasquez/handwriting-synthesis.git"


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if shutil.which("git") is None:
        raise SystemExit("git is required to fetch handwriting-synthesis weights")

    if not REPO_DIR.exists():
        subprocess.run(["git", "clone", REPO_URL, str(REPO_DIR)], check=True)
    else:
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)

    weights_candidates = list(REPO_DIR.rglob("*.npy")) + list(REPO_DIR.rglob("*.npz")) + list(REPO_DIR.rglob("*.pt"))
    print(f"Repository ready at: {REPO_DIR}")
    if weights_candidates:
        print("Found possible weights/files:")
        for item in weights_candidates[:50]:
            print(f" - {item.relative_to(REPO_DIR)}")
    else:
        print("No weights were found automatically.")
        print("Follow the upstream repository instructions, then place/download the model assets under models/handwriting-synthesis/.")


if __name__ == "__main__":
    main()
