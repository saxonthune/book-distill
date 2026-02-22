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

import litellm

from config import load_config, setup_litellm, load_prompt, ROOT


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
    target_lines = config.get("synthesis", {}).get("target_lines", 400)

    prompt_template = load_prompt("synthesize")
    prompt = prompt_template.replace("{extractions}", merged_text).replace("{target_lines}", str(target_lines))

    print(f"Calling {model} for synthesis (target {target_lines} lines)...")
    start = time.time()

    response = litellm.completion(
        model=f"openrouter/{model}",
        messages=[{"role": "user", "content": prompt}],
    )

    elapsed = time.time() - start
    skill_md = response.choices[0].message.content

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

    usage = response.usage
    summary = {
        "model": model,
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
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
