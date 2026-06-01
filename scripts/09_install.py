#!/usr/bin/env python3
"""Step 9: Install the best SKILL.md into ~/.claude/skills/book-summary/.

Picks the best version (first PASS, otherwise v0) and installs
it as a named .md file inside the shared book-summary skill directory.
Also updates the routing table in book-summary/SKILL.md.

Usage:
    python scripts/09_install.py pipeline/<book-name>

Requires pipeline/<book-name>/book-meta.json with:
    {
        "file": "author-short-title.md",
        "author": "Author Name",
        "title": "Full Book Title",
        "year": "2021",
        "summary": "One-paragraph summary for the routing table."
    }

If book-meta.json doesn't exist, the script will prompt interactively.
"""

import json
import re
import shutil
import sys
from pathlib import Path


SKILL_DIR = Path.home() / ".claude" / "skills" / "book-summary"
SKILL_MD = SKILL_DIR / "SKILL.md"


def parse_verdict(report_text: str) -> str:
    for marker in ("**PASS**", "**REVIEW**", "**FAIL**"):
        if marker in report_text:
            return marker.strip("*")
    return "UNKNOWN"


VERDICT_RANK = {"PASS": 3, "REVIEW": 2, "FAIL": 1, "UNKNOWN": 0}


def find_best_skill(pipeline_path: Path) -> tuple[Path, str]:
    """Find the best SKILL.md across v0 and any revisions.

    Picks the version with the best verdict (PASS > REVIEW > FAIL > UNKNOWN).
    Ties break toward the LATEST revision, since each revision is meant to
    fold in fixes — a revision that holds the same verdict as v0 is preferred
    over v0 rather than discarded.
    """
    synth_dir = pipeline_path / "06-synthesized"
    verify_dir = pipeline_path / "07-verified"

    versions = []

    v0_skill = synth_dir / "SKILL.md"
    v0_report = verify_dir / "report.md"
    if v0_skill.exists() and v0_report.exists():
        report_text = v0_report.read_text()
        versions.append(("v0", parse_verdict(report_text), v0_skill))
    elif v0_skill.exists():
        versions.append(("v0", "UNKNOWN", v0_skill))

    rev_num = 1
    while True:
        rev_skill = synth_dir / f"rev-{rev_num}" / "SKILL.md"
        rev_report = verify_dir / f"rev-{rev_num}" / "report.md"
        if not rev_skill.exists():
            break
        if rev_report.exists():
            report_text = rev_report.read_text()
            versions.append((f"rev-{rev_num}", parse_verdict(report_text), rev_skill))
        else:
            versions.append((f"rev-{rev_num}", "UNKNOWN", rev_skill))
        rev_num += 1

    if not versions:
        return v0_skill, "no versions found"

    if len(versions) > 1:
        print("Available versions:")
        for label, verdict, path in versions:
            print(f"  {label:>6}: {verdict}")

    # versions is ordered v0, rev-1, rev-2, ... — i.e. oldest to newest.
    # Pick the best verdict; on a tie, the later (higher-index) version wins.
    best_idx = 0
    for i, v in enumerate(versions):
        if VERDICT_RANK.get(v[1], 0) >= VERDICT_RANK.get(versions[best_idx][1], 0):
            best_idx = i
    best = versions[best_idx]
    return best[2], f"{best[0]} — {best[1]} (best verdict, latest on tie)"


def load_or_prompt_meta(pipeline_path: Path) -> dict:
    """Load book-meta.json or prompt the user interactively."""
    meta_path = pipeline_path / "book-meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        # Validate required fields
        for field in ("file", "author", "title", "year", "summary"):
            if field not in meta:
                print(f"Error: book-meta.json missing required field '{field}'")
                sys.exit(1)
        return meta

    print("No book-meta.json found. Please provide book metadata for the routing table.")
    print()
    author = input("  Author: ").strip()
    title = input("  Title: ").strip()
    year = input("  Year: ").strip()
    summary = input("  Summary (1-2 sentences for routing table): ").strip()

    # Generate filename from author + title
    slug = re.sub(r"[^a-z0-9]+", "-", f"{author.split()[-1]}-{title}".lower()).strip("-")
    # Trim to reasonable length
    slug = "-".join(slug.split("-")[:6])
    default_file = f"{slug}.md"
    file_name = input(f"  Filename [{default_file}]: ").strip() or default_file
    if not file_name.endswith(".md"):
        file_name += ".md"

    meta = {
        "file": file_name,
        "author": author,
        "title": title,
        "year": year,
        "summary": summary,
    }

    # Save for future re-runs
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Saved → {meta_path}")
    print()

    return meta


def update_routing_table(meta: dict) -> None:
    """Add or update an entry in the book-summary SKILL.md routing table."""
    if not SKILL_MD.exists():
        print(f"Warning: {SKILL_MD} not found — skipping routing table update")
        return

    content = SKILL_MD.read_text()
    file_name = meta["file"]
    link = f"[{file_name}]({file_name})"

    new_row = f"| {link} | {meta['author']} | {meta['title']} | {meta['year']} | {meta['summary']} |"

    # Check if this file already has a row
    # Match any row that contains the filename as a link
    pattern = re.compile(r"^\|.*\[" + re.escape(file_name) + r"\].*\|$", re.MULTILINE)
    if pattern.search(content):
        # Replace existing row
        content = pattern.sub(new_row, content)
    else:
        # Insert before the "## How to Use" section (or at end of table)
        # Find the last table row (line starting with | that isn't the header/separator)
        lines = content.split("\n")
        insert_idx = None
        in_table = False
        for i, line in enumerate(lines):
            if line.startswith("| File "):
                in_table = True
            elif in_table and line.startswith("|"):
                insert_idx = i + 1
            elif in_table and not line.startswith("|"):
                break

        if insert_idx is not None:
            lines.insert(insert_idx, new_row)
            content = "\n".join(lines)
        else:
            print("Warning: Could not find routing table in SKILL.md — skipping update")
            return

    SKILL_MD.write_text(content)


def run_install(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    book_name = pipeline_path.name

    meta = load_or_prompt_meta(pipeline_path)
    skill_path, reason = find_best_skill(pipeline_path)

    if not skill_path.exists():
        from config import ROOT
        skill_path = ROOT / "output" / f"{book_name}-skill" / "SKILL.md"

    if not skill_path.exists():
        print(f"Error: No SKILL.md found. Run 06_synthesize.py first.")
        sys.exit(1)

    # Install into book-summary directory
    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    dest = SKILL_DIR / meta["file"]
    shutil.copy2(skill_path, dest)

    # Also copy to output dir
    from config import ROOT
    output_dir = ROOT / "output" / f"{book_name}-skill"
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_path, output_dir / "SKILL.md")

    # Update the routing table
    update_routing_table(meta)

    print(f"Installed: {dest}")
    print(f"  Source:  {skill_path}")
    print(f"  Selected: {reason}")
    print(f"  Size:    {dest.stat().st_size:,} bytes, {len(dest.read_text().splitlines())} lines")
    print(f"  Routing table updated in {SKILL_MD}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/09_install.py pipeline/<book-name>")
        sys.exit(1)
    run_install(sys.argv[1])
