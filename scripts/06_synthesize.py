#!/usr/bin/env python3
"""Step 6: Synthesize merged YAML into a final SKILL.md (strong model).

Usage:
    python scripts/06_synthesize.py pipeline/zinsser-on-writing-well

Output:
    pipeline/<book>/06-synthesized/SKILL.md
    output/<book>-skill/SKILL.md  (copy ready to use)
"""

import json
import sys
import time
from pathlib import Path

import yaml

from config import load_config, load_settings, setup_litellm, load_prompt, stream_completion, ROOT


def density_floor(merged_path: Path) -> tuple[int, int, int]:
    """Compute a target_lines floor from the count of must/should-strength items.

    target_lines from 01b is sized by source word count, but the binding
    constraint on a how-to/reference book is *item density*: a book with
    hundreds of distinct must/should rules needs room to fit them all even
    if its word count is modest. Returns (floor, must_count, should_count).
    """
    try:
        merged = yaml.safe_load(merged_path.read_text())
    except Exception:
        return 0, 0, 0
    must = should = 0
    for key in ("principles", "patterns", "anti_patterns"):
        for item in merged.get(key, []) or []:
            strength = (item.get("strength") or "").strip().lower() if isinstance(item, dict) else ""
            if strength == "must":
                must += 1
            elif strength == "should":
                should += 1
    # ~1 line per must/should item + ~30% overhead for headings/framing,
    # capped so a pathological extraction can't demand a runaway document.
    high_priority = must + should
    floor = min(1000, int(high_priority * 1.3)) if high_priority else 0
    return floor, must, should


def run_synthesis(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    merge_dir = pipeline_path / "05-merged"
    synth_dir = pipeline_path / "06-synthesized"
    synth_dir.mkdir(parents=True, exist_ok=True)

    merged_path = merge_dir / "merged.yaml"
    if not merged_path.exists():
        print(f"Error: {merged_path} not found. Run 05_merge.py first.")
        sys.exit(1)

    merged_text = merged_path.read_text()
    word_count = len(merged_text.split())
    print(f"Merged input: {word_count:,} words")

    config = load_config()
    setup_litellm(config)
    model = config["models"]["synthesis"]
    settings = load_settings(pipeline_path, config)
    target_lines = settings["synthesis"].get("target_lines", 400)

    # Raise the target if the book is dense with high-priority rules — a
    # word-count-derived target can be too tight to fit every must/should item.
    floor, must_n, should_n = density_floor(merged_path)
    if floor > target_lines:
        print(f"  Density floor: {must_n} must + {should_n} should items → "
              f"raising target {target_lines} → {floor} lines")
        target_lines = floor

    prompt_template = load_prompt("synthesize")
    prompt = prompt_template.replace("{extractions}", merged_text).replace("{target_lines}", str(target_lines))

    print(f"Synthesizing with {model} (target {target_lines} lines)...")
    start = time.time()

    skill_md, usage = stream_completion(
        model, [{"role": "user", "content": prompt}], label="Synthesizing"
    )

    elapsed = time.time() - start

    # Strip markdown code fences if the model wrapped it
    if skill_md.startswith("```"):
        lines = skill_md.split("\n")
        # Remove first line (```markdown or ```) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        skill_md = "\n".join(lines)

    # Write to pipeline dir
    synth_path = synth_dir / "SKILL.md"
    synth_path.write_text(skill_md)

    # Also copy to output dir
    book_name = pipeline_path.name
    output_dir = ROOT / "output" / f"{book_name}-skill"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "SKILL.md").write_text(skill_md)

    summary = {
        "model": model,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "elapsed_seconds": round(elapsed, 1),
        "output_lines": len(skill_md.splitlines()),
    }
    (synth_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nDone in {elapsed:.0f}s")
    print(f"  Tokens: {summary['input_tokens']:,} in / {summary['output_tokens']:,} out")
    print(f"  Output: {summary['output_lines']} lines")
    print(f"\n  Pipeline:  {synth_path}")
    print(f"  Ready:     {output_dir / 'SKILL.md'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/06_synthesize.py pipeline/<book-name>")
        sys.exit(1)
    run_synthesis(sys.argv[1])
