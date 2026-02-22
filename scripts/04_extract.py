#!/usr/bin/env python3
"""Step 4: Run LLM extraction on each chunk (parallel, cheap model).

Usage:
    python scripts/04_extract.py pipeline/zinsser-on-writing-well

Output:
    pipeline/<book>/04-extractions/chunk-0001.yaml
    pipeline/<book>/04-extractions/chunk-0002.yaml
    ...
    pipeline/<book>/04-extractions/summary.json
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import litellm
import yaml

from config import load_config, setup_litellm, load_prompt


def extract_chunk(model: str, prompt_template: str, chunk_path: Path) -> dict:
    """Extract structured YAML from a single chunk."""
    chunk_text = chunk_path.read_text()
    prompt = prompt_template.replace("{chunk}", chunk_text)

    response = litellm.completion(
        model=f"openrouter/{model}",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content

    # Extract YAML from response
    yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", raw, re.DOTALL)
    yaml_text = yaml_match.group(1) if yaml_match else raw

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        data = {"_parse_error": True, "_raw": raw}

    usage = response.usage
    return {
        "chunk": chunk_path.name,
        "data": data,
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
    }


def run_extraction(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    chunks_dir = pipeline_path / "03-chunks"
    extract_dir = pipeline_path / "04-extractions"
    extract_dir.mkdir(parents=True, exist_ok=True)

    chunk_files = sorted(chunks_dir.glob("chunk-*.txt"))
    if not chunk_files:
        print(f"Error: No chunks found in {chunks_dir}. Run 03_chunk.py first.")
        sys.exit(1)

    # Skip already-processed chunks
    done = {p.stem for p in extract_dir.glob("chunk-*.yaml")}
    remaining = [f for f in chunk_files if f.stem not in done]

    if done:
        print(f"Resuming: {len(done)} already done, {len(remaining)} remaining")

    if not remaining:
        print("All chunks already extracted.")
        return

    config = load_config()
    setup_litellm(config)
    model = config["models"]["extraction"]
    prompt_template = load_prompt("extract")

    total_count = len(remaining)
    print(f"Extracting {total_count} chunks with {model}...", flush=True)

    total_in = 0
    total_out = 0
    errors = 0
    start = time.time()

    # Parallel extraction — 5 concurrent to stay within rate limits
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(extract_chunk, model, prompt_template, f): f
            for f in remaining
        }

        for i, future in enumerate(as_completed(futures), 1):
            chunk_file = futures[future]
            pct = i * 100 // total_count
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total_count - i) / rate if rate > 0 else 0
            try:
                result = future.result()

                # Write YAML output
                out_path = extract_dir / f"{chunk_file.stem}.yaml"
                out_path.write_text(yaml.dump(result["data"], default_flow_style=False, sort_keys=False, allow_unicode=True))

                total_in += result["input_tokens"]
                total_out += result["output_tokens"]

                if result["data"] and result["data"].get("_parse_error"):
                    errors += 1
                    print(f"  [{i}/{total_count} {pct}%] {chunk_file.name} — YAML parse error (raw saved)  ETA {eta:.0f}s", flush=True)
                else:
                    print(f"  [{i}/{total_count} {pct}%] {chunk_file.name} — ok  ETA {eta:.0f}s", flush=True)

            except Exception as e:
                errors += 1
                print(f"  [{i}/{total_count} {pct}%] {chunk_file.name} — ERROR: {e}", flush=True)

    elapsed = time.time() - start

    # Write summary
    summary = {
        "model": model,
        "total_chunks": len(chunk_files),
        "extracted": len(remaining) - errors,
        "errors": errors,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "elapsed_seconds": round(elapsed, 1),
    }
    (extract_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nDone in {elapsed:.0f}s")
    print(f"  Tokens: {total_in:,} in / {total_out:,} out")
    if errors:
        print(f"  {errors} errors — check raw output or rerun to retry")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/04_extract.py pipeline/<book-name>")
        sys.exit(1)
    run_extraction(sys.argv[1])
