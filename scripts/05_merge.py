#!/usr/bin/env python3
"""Step 5: Merge all per-chunk YAML extractions into a single consolidated file.

Deduplicates and groups by category. This is a local step (no LLM needed).

Usage:
    python scripts/05_merge.py pipeline/zinsser-on-writing-well

Output:
    pipeline/<book>/05-merged/merged.yaml
    pipeline/<book>/05-merged/stats.json
"""

import json
import sys
from pathlib import Path

import yaml


def normalize(text: str) -> str:
    """Lowercase, strip punctuation for dedup comparison."""
    return "".join(c for c in text.lower() if c.isalnum() or c.isspace()).strip()


def dedup_list(items: list[dict], key_field: str) -> list[dict]:
    """Remove near-duplicate items based on a key field."""
    seen = {}
    unique = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key_val = item.get(key_field, "")
        if not key_val:
            unique.append(item)
            continue
        norm = normalize(str(key_val))
        if norm not in seen:
            seen[norm] = True
            unique.append(item)
    return unique


def run_merge(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    extract_dir = pipeline_path / "04-extractions"
    merge_dir = pipeline_path / "05-merged"
    merge_dir.mkdir(parents=True, exist_ok=True)

    yaml_files = sorted(extract_dir.glob("chunk-*.yaml"))
    if not yaml_files:
        print(f"Error: No extractions found in {extract_dir}. Run 04_extract.py first.")
        sys.exit(1)

    # Collect all items by category
    all_principles = []
    all_patterns = []
    all_anti_patterns = []
    all_key_terms = []
    parse_errors = 0

    for yf in yaml_files:
        try:
            data = yaml.safe_load(yf.read_text())
        except yaml.YAMLError:
            parse_errors += 1
            continue

        if not isinstance(data, dict):
            parse_errors += 1
            continue

        if data.get("_parse_error"):
            parse_errors += 1
            continue

        all_principles.extend(data.get("principles", []) or [])
        all_patterns.extend(data.get("patterns", []) or [])
        all_anti_patterns.extend(data.get("anti_patterns", []) or [])
        all_key_terms.extend(data.get("key_terms", []) or [])

    # Dedup
    principles = dedup_list(all_principles, "rule")
    patterns = dedup_list(all_patterns, "name")
    anti_patterns = dedup_list(all_anti_patterns, "name")
    key_terms = dedup_list(all_key_terms, "term")

    merged = {}
    if principles:
        merged["principles"] = principles
    if patterns:
        merged["patterns"] = patterns
    if anti_patterns:
        merged["anti_patterns"] = anti_patterns
    if key_terms:
        merged["key_terms"] = key_terms

    # Write merged YAML
    output_path = merge_dir / "merged.yaml"
    output_path.write_text(yaml.dump(merged, default_flow_style=False, sort_keys=False, allow_unicode=True))

    # Stats
    stats = {
        "source_files": len(yaml_files),
        "parse_errors": parse_errors,
        "before_dedup": {
            "principles": len(all_principles),
            "patterns": len(all_patterns),
            "anti_patterns": len(all_anti_patterns),
            "key_terms": len(all_key_terms),
        },
        "after_dedup": {
            "principles": len(principles),
            "patterns": len(patterns),
            "anti_patterns": len(anti_patterns),
            "key_terms": len(key_terms),
        },
    }
    (merge_dir / "stats.json").write_text(json.dumps(stats, indent=2))

    print(f"Merged {len(yaml_files)} extractions → {output_path}")
    print(f"  Principles: {len(all_principles)} → {len(principles)} (deduped)")
    print(f"  Patterns:   {len(all_patterns)} → {len(patterns)}")
    print(f"  Anti-patterns: {len(all_anti_patterns)} → {len(anti_patterns)}")
    print(f"  Key terms:  {len(all_key_terms)} → {len(key_terms)}")
    if parse_errors:
        print(f"  {parse_errors} files had parse errors")

    # Show merged file size for token estimation
    merged_text = output_path.read_text()
    word_count = len(merged_text.split())
    print(f"\n  Merged file: {word_count:,} words (~{word_count * 4 // 3:,} tokens)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/05_merge.py pipeline/<book-name>")
        sys.exit(1)
    run_merge(sys.argv[1])
