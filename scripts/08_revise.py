#!/usr/bin/env python3
"""Step 9: Verify-revise loop — feed verification gaps back into re-synthesis.

Usage:
    python scripts/09_revise.py pipeline/zinsser-on-writing-well

Reads the v0 verification report. If not PASS, revises the SKILL.md up to
max_revisions times (default 2), re-verifying after each revision.
Artifacts land in 06-synthesized/rev-N/ and 07-verified/rev-N/.
"""

import json
import sys
import time
from pathlib import Path

from config import load_config, load_settings, setup_litellm, load_prompt, stream_completion


def parse_verdict(report_text: str) -> str:
    """Extract PASS/REVIEW/FAIL from a verification report.

    Reads from the '## Verdict' section only — the report prose often mentions
    other verdicts (e.g. "prevent a full **PASS**"), so a whole-document
    substring search would false-match.
    """
    # Isolate the Verdict section if present; otherwise scan the whole report.
    idx = report_text.rfind("## Verdict")
    section = report_text[idx:] if idx != -1 else report_text
    # The actual verdict is the first marker that appears in that section.
    first = None
    for marker in ("**PASS**", "**REVIEW**", "**FAIL**"):
        pos = section.find(marker)
        if pos != -1 and (first is None or pos < first[0]):
            first = (pos, marker)
    return first[1].strip("*") if first else "UNKNOWN"



def run_revision(pipeline_path: str, skill_path: Path, report_path: Path,
                 merged_text: str, rev_num: int, config: dict) -> tuple[Path, Path]:
    """Run one revision cycle: revise SKILL.md, then verify it."""
    model = config["models"].get("revision", config["models"]["synthesis"])
    settings = load_settings(pipeline_path, config)
    target_lines = settings["synthesis"].get("target_lines", 400)

    skill_text = skill_path.read_text()
    report_text = report_path.read_text()

    # Revision is additive: give the model headroom above the current document
    # so it can fold in the flagged gaps WITHOUT dropping existing content to
    # stay under a fixed budget (the old whack-a-mole failure mode). Budget =
    # current length + room for the gaps, capped to avoid runaway growth.
    current_lines = len(skill_text.splitlines())
    gap_count = report_text.count("\n*   ") + report_text.count("\n- ")
    rev_target = min(max(target_lines, current_lines + max(40, gap_count * 4)), current_lines + 250)

    prompt_template = load_prompt("revise")
    prompt = (prompt_template
              .replace("{skill}", skill_text)
              .replace("{report}", report_text)
              .replace("{merged}", merged_text)
              .replace("{target_lines}", str(rev_target)))

    # --- Revise ---
    print(f"\n--- Revision {rev_num} ---")
    start = time.time()

    revised_md, rev_usage = stream_completion(
        model, [{"role": "user", "content": prompt}], label=f"Revising (rev {rev_num})"
    )

    elapsed = time.time() - start

    # Strip markdown code fences if the model wrapped it
    if revised_md.startswith("```"):
        lines = revised_md.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        revised_md = "\n".join(lines)

    rev_synth_dir = pipeline_path / "06-synthesized" / f"rev-{rev_num}"
    rev_synth_dir.mkdir(parents=True, exist_ok=True)
    rev_skill_path = rev_synth_dir / "SKILL.md"
    rev_skill_path.write_text(revised_md)

    summary = {
        "model": model,
        "revision": rev_num,
        "input_tokens": rev_usage["input_tokens"],
        "output_tokens": rev_usage["output_tokens"],
        "elapsed_seconds": round(elapsed, 1),
        "output_lines": len(revised_md.splitlines()),
    }
    (rev_synth_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"  Revised in {elapsed:.0f}s — {len(revised_md.splitlines())} lines")

    # --- Verify ---
    verify_model = config["models"].get("verification", config["models"]["extraction"])
    verify_prompt_template = load_prompt("verify")
    verify_prompt = (verify_prompt_template
                     .replace("{merged}", merged_text)
                     .replace("{skill}", revised_md))

    start = time.time()

    report, v_usage = stream_completion(
        verify_model, [{"role": "user", "content": verify_prompt}], label=f"Verifying (rev {rev_num})"
    )

    elapsed = time.time() - start

    if report.startswith("```"):
        lines = report.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        report = "\n".join(lines)

    rev_verify_dir = pipeline_path / "07-verified" / f"rev-{rev_num}"
    rev_verify_dir.mkdir(parents=True, exist_ok=True)
    rev_report_path = rev_verify_dir / "report.md"
    rev_report_path.write_text(report)

    v_summary = {
        "model": verify_model,
        "revision": rev_num,
        "input_tokens": v_usage["input_tokens"],
        "output_tokens": v_usage["output_tokens"],
        "elapsed_seconds": round(elapsed, 1),
    }
    (rev_verify_dir / "summary.json").write_text(json.dumps(v_summary, indent=2))

    verdict = parse_verdict(report)
    print(f"  Verified in {elapsed:.0f}s — {verdict}")

    return rev_skill_path, rev_report_path


def run_revise_loop(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    synth_dir = pipeline_path / "06-synthesized"
    verify_dir = pipeline_path / "07-verified"
    merge_dir = pipeline_path / "05-merged"

    v0_report_path = verify_dir / "report.md"
    v0_skill_path = synth_dir / "SKILL.md"
    merged_path = merge_dir / "merged.yaml"

    for path, label in [(v0_report_path, "07_verify.py"), (v0_skill_path, "06_synthesize.py"), (merged_path, "05_merge.py")]:
        if not path.exists():
            print(f"Error: {path} not found. Run {label} first.")
            sys.exit(1)

    v0_report = v0_report_path.read_text()
    v0_verdict = parse_verdict(v0_report)

    print(f"v0: {v0_verdict}")

    if v0_verdict == "PASS":
        print("v0 already passes — no revisions needed.")
        return

    config = load_config()
    setup_litellm(config)
    max_revisions = config.get("max_revisions", 1)
    merged_text = merged_path.read_text()

    # Track all versions: (version_label, verdict, skill_path)
    versions = [("v0", v0_verdict, v0_skill_path)]

    current_skill = v0_skill_path
    current_report = v0_report_path

    for rev in range(1, max_revisions + 1):
        rev_skill, rev_report = run_revision(
            pipeline_path, current_skill, current_report,
            merged_text, rev, config,
        )
        report_text = rev_report.read_text()
        verdict = parse_verdict(report_text)
        versions.append((f"rev-{rev}", verdict, rev_skill))

        current_skill = rev_skill
        current_report = rev_report

        if verdict == "PASS":
            print(f"\nrev-{rev} passes — stopping early.")
            break

    # Summary
    print("\n=== Revision Summary ===")
    for label, verdict, path in versions:
        print(f"  {label:>6}: {verdict:<6}  {path}")

    # Find best: highest-ranked verdict; on a tie, the latest revision wins
    # (each revision folds in fixes, so an equal-verdict revision beats v0).
    verdict_rank = {"PASS": 3, "REVIEW": 2, "FAIL": 1, "UNKNOWN": 0}
    best = versions[0]
    for v in versions:
        if verdict_rank.get(v[1], 0) >= verdict_rank.get(best[1], 0):
            best = v

    print(f"\nBest version: {best[0]} ({best[1]})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/09_revise.py pipeline/<book-name>")
        sys.exit(1)
    run_revise_loop(sys.argv[1])
