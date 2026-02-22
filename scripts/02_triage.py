#!/usr/bin/env python3
"""Step 2: Analyze TOC and suggest chapter triage (extract/summarize/skip).

Produces a YAML file for human review before chunking.

Usage:
    python scripts/02_triage.py pipeline/zinsser-on-writing-well

Output:
    pipeline/<book>/02-triage/triage.yaml
"""

import json
import re
import sys
from pathlib import Path

import litellm
import yaml

from config import load_config, setup_litellm, load_prompt


def run_triage(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    pages_dir = pipeline_path / "01-pages"
    triage_dir = pipeline_path / "02-triage"
    triage_dir.mkdir(parents=True, exist_ok=True)

    toc_file = pages_dir / "toc.txt"
    if not toc_file.exists():
        print("No TOC found. Skipping triage — all pages will be processed.")
        print("You can manually create 02-triage/triage.yaml if needed.")
        return

    toc_text = toc_file.read_text()
    print(f"TOC loaded ({len(toc_text.splitlines())} entries)")

    config = load_config()
    setup_litellm(config)
    model = config["models"]["triage"]

    prompt_template = load_prompt("triage")
    prompt = prompt_template.replace("{toc}", toc_text)

    print(f"Calling {model} for triage suggestions...")
    response = litellm.completion(
        model=f"openrouter/{model}",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content

    # Extract YAML from response (may be wrapped in ```yaml ... ```)
    yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", raw, re.DOTALL)
    yaml_text = yaml_match.group(1) if yaml_match else raw

    # Validate it parses
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        print(f"Warning: LLM output wasn't valid YAML: {e}")
        print("Saving raw output for manual editing.")
        (triage_dir / "triage-raw.txt").write_text(raw)
        return

    # Write the triage file
    output_path = triage_dir / "triage.yaml"
    output_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    # Print summary
    chapters = data.get("chapters", [])
    counts = {"extract": 0, "summarize": 0, "skip": 0}
    for ch in chapters:
        t = ch.get("treatment", "extract")
        counts[t] = counts.get(t, 0) + 1

    print(f"\nTriage → {output_path}")
    print(f"  extract: {counts['extract']}  summarize: {counts['summarize']}  skip: {counts['skip']}")
    print(f"\n  Review and edit triage.yaml before running 03_chunk.py")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/02_triage.py pipeline/<book-name>")
        sys.exit(1)
    run_triage(sys.argv[1])
