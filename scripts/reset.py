#!/usr/bin/env python3
"""Reset pipeline artifacts from a given step onward.

Usage:
    python scripts/reset.py pipeline/my-book --from 03
    python scripts/reset.py pipeline/my-book --from 04

Deletes step directories from the specified step onward.
Preserves settings.json and never touches output/.
"""

import shutil
import sys
from pathlib import Path

STEP_DIRS = [
    "01-pages",
    "02-triage",
    "03-chunks",
    "04-extractions",
    "05-merged",
    "06-synthesized",
    "07-verified",
]

# Map step prefixes to index
STEP_PREFIXES = {d.split("-")[0]: i for i, d in enumerate(STEP_DIRS)}


def run_reset(pipeline_path: str, from_step: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()

    if not pipeline_path.exists():
        print(f"Error: {pipeline_path} not found.")
        sys.exit(1)

    if from_step not in STEP_PREFIXES:
        valid = ", ".join(sorted(STEP_PREFIXES.keys()))
        print(f"Error: Unknown step '{from_step}'. Valid steps: {valid}")
        sys.exit(1)

    start_idx = STEP_PREFIXES[from_step]
    to_delete = STEP_DIRS[start_idx:]

    deleted = []
    for step_dir_name in to_delete:
        step_dir = pipeline_path / step_dir_name
        if step_dir.exists():
            shutil.rmtree(step_dir)
            deleted.append(step_dir_name)

    if deleted:
        print(f"Deleted: {', '.join(deleted)}")
    else:
        print("Nothing to delete.")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[2] != "--from":
        print("Usage: python scripts/reset.py pipeline/<book-name> --from <step>")
        print("Steps: 01, 02, 03, 04, 05, 06, 07")
        sys.exit(1)
    run_reset(sys.argv[1], sys.argv[3])
