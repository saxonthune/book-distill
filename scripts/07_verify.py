#!/usr/bin/env python3
"""Step 7: Verify synthesis coverage against merged extractions (LLM).

Usage:
    python scripts/07_verify.py pipeline/zinsser-on-writing-well

Output:
    pipeline/<book>/07-verified/report.md
"""

import json
import sys
import time
from pathlib import Path

from config import load_config, setup_litellm, load_prompt, stream_completion


def run_verification(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    merge_dir = pipeline_path / "05-merged"
    synth_dir = pipeline_path / "06-synthesized"
    verify_dir = pipeline_path / "07-verified"
    verify_dir.mkdir(parents=True, exist_ok=True)

    merged_path = merge_dir / "merged.yaml"
    skill_path = synth_dir / "SKILL.md"

    if not merged_path.exists():
        print(f"Error: {merged_path} not found. Run 05_merge.py first.")
        sys.exit(1)
    if not skill_path.exists():
        print(f"Error: {skill_path} not found. Run 06_synthesize.py first.")
        sys.exit(1)

    merged_text = merged_path.read_text()
    skill_text = skill_path.read_text()
    print(f"Merged input: {len(merged_text.split()):,} words")
    print(f"SKILL.md: {len(skill_text.splitlines())} lines")

    config = load_config()
    setup_litellm(config)
    model = config["models"].get("verification", config["models"]["extraction"])

    prompt_template = load_prompt("verify")
    prompt = prompt_template.replace("{merged}", merged_text).replace("{skill}", skill_text)

    print(f"Verifying with {model}...")
    start = time.time()

    report, usage = stream_completion(
        model, [{"role": "user", "content": prompt}], label="Verifying"
    )

    elapsed = time.time() - start

    # Strip markdown code fences if the model wrapped it
    if report.startswith("```"):
        lines = report.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        report = "\n".join(lines)

    report_path = verify_dir / "report.md"
    report_path.write_text(report)

    summary = {
        "model": model,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "elapsed_seconds": round(elapsed, 1),
    }
    (verify_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    # Print verdict line if found
    for line in report.splitlines():
        if line.startswith("## Verdict") or "**PASS**" in line or "**REVIEW**" in line or "**FAIL**" in line:
            print(f"  {line.strip()}")

    print(f"\nDone in {elapsed:.0f}s")
    print(f"  Tokens: {summary['input_tokens']:,} in / {summary['output_tokens']:,} out")
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/07_verify.py pipeline/<book-name>")
        sys.exit(1)
    run_verification(sys.argv[1])
