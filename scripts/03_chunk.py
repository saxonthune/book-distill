#!/usr/bin/env python3
"""Step 3: Split extracted page text into sized chunks for LLM extraction.

Reads triage decisions from 02-triage/ if available, otherwise processes all pages.

Usage:
    python scripts/03_chunk.py pipeline/my-book

Output:
    pipeline/my-book/03-chunks/chunk-001.txt
    pipeline/my-book/03-chunks/chunk-002.txt
    ...
    pipeline/my-book/03-chunks/manifest.json
"""

import json
import sys
from pathlib import Path

from config import load_config, load_settings, ROOT


def load_triage(pipeline_path: Path) -> dict | None:
    """Load triage decisions if they exist."""
    triage_file = pipeline_path / "02-triage" / "triage.yaml"
    if not triage_file.exists():
        return None
    import yaml
    with open(triage_file) as f:
        data = yaml.safe_load(f)
    return data


def load_toc_chapters(pages_dir: Path) -> list[dict]:
    """Parse toc.txt to extract top-level chapter start pages.

    Returns list of {"number": "1", "title": "...", "start_page": 13}.
    """
    toc_file = pages_dir / "toc.txt"
    if not toc_file.exists():
        return []

    import re
    entries = []
    for line in toc_file.read_text().splitlines():
        # Top-level entries are not indented: "1 Title here (p.13)"
        m = re.match(r"^(\w+)\s+(.+?)\s+\(p\.(\d+)\)\s*$", line)
        if m:
            entries.append({
                "number": m.group(1),
                "title": m.group(2),
                "start_page": int(m.group(3)),
            })
    return entries


def get_page_ranges_to_skip(triage: dict | None, meta: dict, pages_dir: Path) -> set[int]:
    """Return page numbers to skip based on triage decisions + TOC page ranges."""
    if not triage or "chapters" not in triage:
        return set()

    toc_chapters = load_toc_chapters(pages_dir)
    if not toc_chapters:
        return set()

    # Build number → start_page lookup from TOC
    toc_lookup = {ch["number"]: ch["start_page"] for ch in toc_chapters}
    total_pages = meta.get("total_pages", 0)

    # Resolve start/end pages for each triage chapter
    triage_chapters = triage["chapters"]
    resolved = []
    for ch in triage_chapters:
        num = str(ch.get("number", ""))
        start = ch.get("start_page") or toc_lookup.get(num)
        if start is None:
            continue
        resolved.append({"start_page": start, "treatment": ch.get("treatment", "extract")})

    # Sort by start page and compute end pages
    resolved.sort(key=lambda c: c["start_page"])
    for i, ch in enumerate(resolved):
        if i + 1 < len(resolved):
            ch["end_page"] = resolved[i + 1]["start_page"] - 1
        else:
            ch["end_page"] = total_pages

    # Pages before first chapter are front matter — skip
    skip_pages = set()
    if resolved:
        for p in range(1, resolved[0]["start_page"]):
            skip_pages.add(p)

    # Skip pages in "skip" chapters
    for ch in resolved:
        if ch["treatment"] == "skip":
            for p in range(ch["start_page"], ch["end_page"] + 1):
                skip_pages.add(p)

    return skip_pages


def load_pages(pages_dir: Path, skip_pages: set[int]) -> list[tuple[int, str]]:
    """Load page/chapter text files, skipping specified pages. Returns (num, text) pairs."""
    pages = []
    # Support both PDF (page-*.txt) and EPUB (ch-*.txt) formats
    page_files = sorted(pages_dir.glob("page-*.txt")) or sorted(pages_dir.glob("ch-*.txt"))
    for page_file in page_files:
        # Extract number from filename like page-0001.txt or ch-0001.txt
        page_num = int(page_file.stem.split("-")[1])
        if page_num in skip_pages:
            continue
        text = page_file.read_text().strip()
        if text:
            pages.append((page_num, text))
    return pages


def chunk_pages(pages: list[tuple[int, str]], max_words: int, overlap_words: int) -> list[dict]:
    """Combine pages into chunks of approximately max_words, with overlap."""
    chunks = []
    current_words = []
    current_pages = []
    current_word_count = 0

    for page_num, text in pages:
        words = text.split()
        current_words.extend(words)
        current_pages.append(page_num)
        current_word_count += len(words)

        if current_word_count >= max_words:
            chunk_text = " ".join(current_words)
            chunks.append({
                "pages": list(current_pages),
                "word_count": current_word_count,
                "text": chunk_text,
            })

            # Keep overlap from the end of this chunk
            if overlap_words > 0:
                overlap = current_words[-overlap_words:]
                current_words = overlap
                current_word_count = len(overlap)
                current_pages = [current_pages[-1]]
            else:
                current_words = []
                current_word_count = 0
                current_pages = []

    # Final chunk
    if current_words:
        chunks.append({
            "pages": list(current_pages),
            "word_count": current_word_count,
            "text": " ".join(current_words),
        })

    return chunks


def run_chunking(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    pages_dir = pipeline_path / "01-pages"
    chunks_dir = pipeline_path / "03-chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    if not pages_dir.exists():
        print(f"Error: {pages_dir} not found. Run 01_extract_text.py first.")
        sys.exit(1)

    # Load metadata
    meta_file = pages_dir / "meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}

    # Load config, with per-book settings override
    config = load_config()
    settings = load_settings(pipeline_path, config)
    chunk_cfg = settings["chunking"]
    max_words = chunk_cfg.get("max_words", 500)
    overlap_words = chunk_cfg.get("overlap_words", 50)

    # Load triage decisions
    triage = load_triage(pipeline_path)
    skip_pages = get_page_ranges_to_skip(triage, meta, pages_dir)
    if skip_pages:
        print(f"Triage: skipping {len(skip_pages)} pages")

    # Load pages
    pages = load_pages(pages_dir, skip_pages)
    print(f"Loaded {len(pages)} non-empty pages")

    # Chunk
    chunks = chunk_pages(pages, max_words, overlap_words)
    print(f"Created {len(chunks)} chunks (target ~{max_words} words each)")

    # Write chunks
    manifest = []
    for i, chunk in enumerate(chunks):
        chunk_file = chunks_dir / f"chunk-{i + 1:04d}.txt"
        chunk_file.write_text(chunk["text"])
        entry = {
            "file": chunk_file.name,
            "pages": chunk["pages"],
            "word_count": chunk["word_count"],
        }
        manifest.append(entry)

    # Write manifest
    manifest_path = chunks_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest → {manifest_path}")

    # Summary
    total_words = sum(c["word_count"] for c in chunks)
    print(f"Total: {total_words:,} words across {len(chunks)} chunks")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/03_chunk.py pipeline/<book-name>")
        sys.exit(1)
    run_chunking(sys.argv[1])
