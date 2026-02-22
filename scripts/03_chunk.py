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

from config import load_config, ROOT


def load_triage(pipeline_path: Path) -> dict | None:
    """Load triage decisions if they exist."""
    triage_file = pipeline_path / "02-triage" / "triage.yaml"
    if not triage_file.exists():
        return None
    import yaml
    with open(triage_file) as f:
        data = yaml.safe_load(f)
    return data


def get_page_ranges_to_skip(triage: dict | None, meta: dict) -> set[int]:
    """Return page numbers to skip based on triage decisions."""
    if not triage or "chapters" not in triage:
        return set()

    skip_pages = set()
    chapters = triage["chapters"]
    for i, ch in enumerate(chapters):
        if ch.get("treatment") == "skip":
            start = ch.get("start_page", 0)
            # End page is the start of next chapter, or end of book
            if i + 1 < len(chapters):
                end = chapters[i + 1].get("start_page", start)
            else:
                end = meta.get("total_pages", start) + 1
            for p in range(start, end):
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

    # Load config for chunk sizing
    config = load_config()
    chunk_cfg = config.get("chunking", {})
    max_words = chunk_cfg.get("max_words", 500)
    overlap_words = chunk_cfg.get("overlap_words", 50)

    # Load triage decisions
    triage = load_triage(pipeline_path)
    skip_pages = get_page_ranges_to_skip(triage, meta)
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
