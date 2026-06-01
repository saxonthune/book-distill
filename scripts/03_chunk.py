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
import re
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


def _norm_title(title: str) -> str:
    """Normalize a chapter title for fuzzy matching (lowercase, alnum-only)."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def load_toc_chapters(pages_dir: Path) -> list[dict]:
    """Parse toc.txt to extract top-level chapter start pages.

    Lines are written by format_toc as "{title} (p.{page})", with sub-levels
    indented by two spaces. Only top-level (non-indented) entries are returned.
    Titles may be one or many words and carry no leading chapter number.

    Returns list of {"title": "...", "start_page": 13}.
    """
    toc_file = pages_dir / "toc.txt"
    if not toc_file.exists():
        return []

    entries = []
    for line in toc_file.read_text().splitlines():
        # Top-level entries start with a non-space char (sub-entries are indented).
        m = re.match(r"^(\S.*?)\s+\(p\.(\d+)\)\s*$", line)
        if m:
            entries.append({
                "title": m.group(1).strip(),
                "start_page": int(m.group(2)),
            })
    return entries


def get_page_ranges_to_skip(triage: dict | None, meta: dict, pages_dir: Path) -> set[int]:
    """Return page numbers to skip based on triage decisions + TOC page ranges.

    Triage chapters are resolved to real page/file ranges by matching their
    title against the TOC (an explicit ``start_page`` on the triage entry wins).
    This is fail-safe: a ``skip`` chapter that cannot be confidently matched to
    a TOC entry is KEPT (not skipped) and reported, because a wrong skip
    silently deletes real content whereas a wrong keep only adds cheap noise
    that washes out in merge/synthesis. All skip/keep decisions are logged.
    """
    if not triage or "chapters" not in triage:
        return set()

    toc_chapters = load_toc_chapters(pages_dir)
    if not toc_chapters:
        return set()

    total_pages = meta.get("total_pages", 0)

    # Resolve each TOC chapter's [start_page, end_page] range over the real files.
    toc = sorted(toc_chapters, key=lambda c: c["start_page"])
    for i, ch in enumerate(toc):
        ch["end_page"] = toc[i + 1]["start_page"] - 1 if i + 1 < len(toc) else total_pages
    by_title = {_norm_title(c["title"]): c for c in toc}
    by_start = {c["start_page"]: c for c in toc}

    skip_pages = set()
    skipped, kept_unresolved = [], []
    for ch in triage["chapters"]:
        if ch.get("treatment") != "skip":
            continue
        title = ch.get("title", "")
        # Prefer an explicit start_page; otherwise match by normalized title.
        match = by_start.get(ch.get("start_page")) if ch.get("start_page") else None
        if match is None:
            match = by_title.get(_norm_title(title))
        if match is None:
            kept_unresolved.append(title or "(untitled)")
            continue
        for p in range(match["start_page"], match["end_page"] + 1):
            skip_pages.add(p)
        skipped.append((title or match["title"], match["start_page"], match["end_page"]))

    # Pages before the first TOC chapter are front matter — skip them.
    front = range(1, toc[0]["start_page"])
    skip_pages.update(front)

    if front:
        print(f"  Triage: skipping {len(front)} front-matter page(s) before first chapter")
    for title, s, e in skipped:
        print(f"  Triage: skip '{title}' (p.{s}-{e})")
    if kept_unresolved:
        print(f"  Triage: KEEPING {len(kept_unresolved)} 'skip' chapter(s) that could not be "
              f"matched to a TOC entry (fail-safe — review if unexpected):")
        for title in kept_unresolved:
            print(f"    - keep '{title}'")

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

    for page_num, text in pages:
        words = text.split()
        current_words.extend(words)
        if not current_pages or current_pages[-1] != page_num:
            current_pages.append(page_num)

        # Emit as many full chunks as the accumulated text allows. This splits
        # within a single oversized page/chapter (e.g. EPUB chapters that are
        # thousands of words) rather than emitting one giant chunk per page.
        while len(current_words) >= max_words:
            chunk_words = current_words[:max_words]
            chunks.append({
                "pages": list(current_pages),
                "word_count": len(chunk_words),
                "text": " ".join(chunk_words),
            })

            # Carry overlap into the next chunk; stay anchored to the current page.
            cut = max_words - overlap_words if overlap_words > 0 else max_words
            current_words = current_words[cut:]
            current_pages = [page_num]

    # Final chunk
    if current_words:
        chunks.append({
            "pages": list(current_pages),
            "word_count": len(current_words),
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
