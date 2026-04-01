#!/usr/bin/env python3
"""Step 1b: Compute pipeline settings based on source length and density.

Analyzes extracted pages and writes settings.json with tuned parameters.
By default, uses deterministic heuristics. With --ai, calls an LLM to
refine recommendations based on a sample of the text.

Usage:
    python scripts/01b_settings.py pipeline/my-book
    python scripts/01b_settings.py pipeline/my-book --ai

Output:
    pipeline/my-book/settings.json
"""

import json
import sys
import time
from pathlib import Path

from config import load_config, setup_litellm, ROOT


def count_words(pages_dir: Path) -> tuple[int, int, list[str]]:
    """Count total words, page count, and collect sample texts."""
    page_files = sorted(pages_dir.glob("page-*.txt")) or sorted(pages_dir.glob("ch-*.txt"))
    total_words = 0
    page_count = 0
    samples = []
    for pf in page_files:
        text = pf.read_text().strip()
        if not text:
            continue
        page_count += 1
        total_words += len(text.split())
        # Sample first, middle, and last non-empty pages
        samples.append(text)

    picked = []
    if samples:
        picked.append(samples[0][:500])
        if len(samples) > 2:
            picked.append(samples[len(samples) // 2][:500])
        if len(samples) > 1:
            picked.append(samples[-1][:500])

    return total_words, page_count, picked


def deterministic_settings(total_words: int, page_count: int) -> dict:
    """Compute settings from word count using simple thresholds."""
    # Chunk sizing: shorter works get larger chunks for more context
    if total_words < 10_000:
        max_words = 1500
        overlap_words = 100
    elif total_words < 30_000:
        max_words = 1000
        overlap_words = 75
    elif total_words < 80_000:
        max_words = 500
        overlap_words = 50
    else:
        max_words = 500
        overlap_words = 50

    # Target lines: scale with source size, with a floor and ceiling
    # Rough heuristic: 1 output line per 30 input words, clamped
    raw_target = total_words // 30
    target_lines = max(150, min(600, raw_target))

    return {
        "chunking": {
            "max_words": max_words,
            "overlap_words": overlap_words,
        },
        "synthesis": {
            "target_lines": target_lines,
        },
        "_computed": {
            "total_words": total_words,
            "page_count": page_count,
            "compression_ratio": round(total_words / max(target_lines * 8, 1), 1),
        },
    }


def ai_refine(settings: dict, samples: list[str], config: dict) -> dict:
    """Call LLM to refine settings based on text samples."""
    import litellm

    sample_text = "\n\n---\n\n".join(samples)
    total_words = settings["_computed"]["total_words"]
    page_count = settings["_computed"]["page_count"]

    prompt = f"""You are tuning a book-to-skill distillation pipeline. Based on the source material below, recommend pipeline settings.

Source stats:
- {page_count} pages, {total_words:,} total words

Text samples (first/middle/last pages):
{sample_text}

Current defaults (computed from length):
- chunk max_words: {settings["chunking"]["max_words"]}
- chunk overlap_words: {settings["chunking"]["overlap_words"]}
- synthesis target_lines: {settings["synthesis"]["target_lines"]}

Consider:
- Dense academic/technical text benefits from larger chunks (more context per extraction) and higher target_lines (less compression)
- Light/repetitive prose can use smaller chunks and lower target_lines
- Very short works (<20 pages) should preserve almost everything

Respond with ONLY a JSON object (no markdown fencing) with these keys:
- chunking.max_words (int)
- chunking.overlap_words (int)
- synthesis.target_lines (int)
- reasoning (string, 1-2 sentences)"""

    model = config["models"].get("triage", config["models"]["extraction"])
    print(f"Calling {model} for settings recommendation...")
    start = time.time()

    response = litellm.completion(
        model=f"openrouter/{model}",
        messages=[{"role": "user", "content": prompt}],
    )

    elapsed = time.time() - start
    raw = response.choices[0].message.content.strip()

    # Strip code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        raw = "\n".join(lines)

    try:
        rec = json.loads(raw)
        settings["chunking"]["max_words"] = rec.get("chunking", {}).get("max_words", settings["chunking"]["max_words"])
        settings["chunking"]["overlap_words"] = rec.get("chunking", {}).get("overlap_words", settings["chunking"]["overlap_words"])
        settings["synthesis"]["target_lines"] = rec.get("synthesis", {}).get("target_lines", settings["synthesis"]["target_lines"])
        settings["_ai_reasoning"] = rec.get("reasoning", "")
        print(f"  AI reasoning: {settings['_ai_reasoning']}")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Warning: Could not parse AI response ({e}), keeping deterministic defaults")
        settings["_ai_reasoning"] = f"Parse error: {raw[:200]}"

    print(f"  Done in {elapsed:.0f}s")
    return settings


def run_settings(pipeline_path: str, use_ai: bool = False) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    pages_dir = pipeline_path / "01-pages"

    if not pages_dir.exists():
        print(f"Error: {pages_dir} not found. Run 01_extract_text.py first.")
        sys.exit(1)

    total_words, page_count, samples = count_words(pages_dir)
    print(f"Source: {page_count} pages, {total_words:,} words")

    settings = deterministic_settings(total_words, page_count)

    if use_ai:
        config = load_config()
        setup_litellm(config)
        settings = ai_refine(settings, samples, config)

    settings_path = pipeline_path / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2))

    print(f"\nSettings → {settings_path}")
    print(f"  chunk max_words:    {settings['chunking']['max_words']}")
    print(f"  chunk overlap:      {settings['chunking']['overlap_words']}")
    print(f"  synthesis target:   {settings['synthesis']['target_lines']} lines")
    print(f"  compression ratio:  {settings['_computed']['compression_ratio']}:1")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/01b_settings.py pipeline/<book-name> [--ai]")
        sys.exit(1)
    use_ai = "--ai" in sys.argv
    run_settings(sys.argv[1], use_ai=use_ai)
