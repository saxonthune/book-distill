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


def extract_year(meta: dict) -> str | None:
    """Try to extract publication year from metadata or source filename."""
    # Check source filename for (YYYY) pattern
    source = meta.get("source", "")
    m = re.search(r"\((\d{4})\)", source)
    if m:
        return m.group(1)
    return None


def generate_book_meta(pipeline_path: Path, meta: dict, model: str,
                       toc_text: str | None = None) -> None:
    """Generate book-meta.json using available metadata + LLM for summary."""
    meta_path = pipeline_path / "book-meta.json"
    if meta_path.exists():
        print(f"  book-meta.json already exists, skipping")
        return

    book_name = meta.get("book_name", pipeline_path.name)
    title = meta.get("title")
    author = meta.get("author")
    year = extract_year(meta)
    first_page = meta.get("first_page_text", "")

    # Build context for LLM to generate title/author/summary
    context_parts = []
    if title:
        context_parts.append(f"Title: {title}")
    if author:
        context_parts.append(f"Author: {author}")
    if year:
        context_parts.append(f"Year: {year}")
    if toc_text:
        context_parts.append(f"Table of contents:\n{toc_text[:2000]}")
    if first_page:
        context_parts.append(f"First page text:\n{first_page[:1000]}")
    context_parts.append(f"Source filename: {meta.get('source', '')}")

    context = "\n\n".join(context_parts)

    prompt = f"""Based on the following information about a book, provide a JSON object with these fields:
- "author": full author name
- "title": book title (short, no subtitle)
- "year": publication year (string)
- "summary": one-sentence summary of the book's core content and thesis

Only output the JSON object, no commentary.

{context}"""

    response = litellm.completion(
        model=f"openrouter/{model}",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content or ""
    # Extract JSON from response
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            book_meta = {
                "file": f"{book_name}.md",
                "author": data.get("author", author or "Unknown"),
                "title": data.get("title", title or book_name),
                "year": data.get("year", year or "Unknown"),
                "summary": data.get("summary", ""),
            }
            meta_path.write_text(json.dumps(book_meta, indent=2))
            print(f"  book-meta.json generated: {book_meta['author']} — {book_meta['title']} ({book_meta['year']})")
            return
        except json.JSONDecodeError:
            pass

    # Fallback: write what we have without summary
    book_meta = {
        "file": f"{book_name}.md",
        "author": author or "Unknown",
        "title": title or book_name,
        "year": year or "Unknown",
        "summary": "",
    }
    meta_path.write_text(json.dumps(book_meta, indent=2))
    print(f"  book-meta.json generated (no summary — LLM parse failed)")


def run_triage(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    pages_dir = pipeline_path / "01-pages"
    triage_dir = pipeline_path / "02-triage"
    triage_dir.mkdir(parents=True, exist_ok=True)

    # Load page metadata
    meta_file = pages_dir / "meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}

    config = load_config()
    setup_litellm(config)
    model = config["models"]["triage"]

    toc_file = pages_dir / "toc.txt"
    toc_text = toc_file.read_text() if toc_file.exists() else None

    # Generate book-meta.json
    print("Generating book metadata...")
    generate_book_meta(pipeline_path, meta, model, toc_text)

    if not toc_text:
        print("No TOC found. Skipping triage — all pages will be processed.")
        print("You can manually create 02-triage/triage.yaml if needed.")
        return

    print(f"TOC loaded ({len(toc_text.splitlines())} entries)")

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
