#!/usr/bin/env python3
"""Step 3v: Group pages into chapter-based chunks for vision extraction.

Uses the TOC to group pages by chapter. Falls back to fixed-size page groups
when no TOC is available. Each chunk references page images in 01-pages/
rather than containing concatenated text.

Usage:
    python scripts/03v_chunk_chapters.py pipeline/my-book

Output:
    pipeline/my-book/03-chunks/manifest.json
"""

import json
import sys
from pathlib import Path

import importlib
_chunk_mod = importlib.import_module("03_chunk")
load_triage = _chunk_mod.load_triage
load_toc_chapters = _chunk_mod.load_toc_chapters
get_page_ranges_to_skip = _chunk_mod.get_page_ranges_to_skip

from config import load_config, load_settings, ROOT


def chapters_to_page_ranges(
    chapters: list[dict],
    total_pages: int,
    skip_pages: set[int],
) -> list[dict]:
    """Convert TOC chapters into page ranges with skip filtering.

    Returns list of {"title": str, "start": int, "end": int, "pages": list[int]}.
    """
    if not chapters:
        return []

    # Sort by start page
    sorted_chs = sorted(chapters, key=lambda c: c["start_page"])

    ranges = []
    for i, ch in enumerate(sorted_chs):
        start = ch["start_page"]
        end = sorted_chs[i + 1]["start_page"] - 1 if i + 1 < len(sorted_chs) else total_pages
        pages = [p for p in range(start, end + 1) if p not in skip_pages]
        if pages:
            ranges.append({
                "title": ch["title"],
                "start": start,
                "end": end,
                "pages": pages,
            })

    return ranges


def split_large_chapters(
    chapter_ranges: list[dict],
    max_pages: int,
) -> list[dict]:
    """Split any chapter exceeding max_pages into sub-groups."""
    result = []
    for ch in chapter_ranges:
        pages = ch["pages"]
        if len(pages) <= max_pages:
            result.append(ch)
        else:
            # Split into parts
            for part_idx in range(0, len(pages), max_pages):
                part_pages = pages[part_idx:part_idx + max_pages]
                part_num = part_idx // max_pages + 1
                total_parts = (len(pages) + max_pages - 1) // max_pages
                result.append({
                    "title": f"{ch['title']} (part {part_num}/{total_parts})",
                    "start": part_pages[0],
                    "end": part_pages[-1],
                    "pages": part_pages,
                })
    return result


def add_overlap(groups: list[dict], overlap_pages: int) -> list[dict]:
    """Add overlap pages from the end of each group to the start of the next."""
    if overlap_pages <= 0 or len(groups) <= 1:
        return groups

    result = [groups[0]]
    for i in range(1, len(groups)):
        prev_pages = groups[i - 1]["pages"]
        overlap = prev_pages[-overlap_pages:]
        group = groups[i].copy()
        group["pages"] = overlap + group["pages"]
        result.append(group)
    return result


def fallback_grouping(
    total_pages: int,
    skip_pages: set[int],
    group_size: int,
) -> list[dict]:
    """Group pages in fixed-size batches when no TOC exists."""
    all_pages = [p for p in range(1, total_pages + 1) if p not in skip_pages]
    groups = []
    for i in range(0, len(all_pages), group_size):
        batch = all_pages[i:i + group_size]
        groups.append({
            "title": f"Pages {batch[0]}-{batch[-1]}",
            "start": batch[0],
            "end": batch[-1],
            "pages": batch,
        })
    return groups


def run_vision_chunking(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    pages_dir = pipeline_path / "01-pages"
    chunks_dir = pipeline_path / "03-chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    if not pages_dir.exists():
        print(f"Error: {pages_dir} not found. Run 01v_extract_images.py first.")
        sys.exit(1)

    # Load metadata
    meta_file = pages_dir / "meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    total_pages = meta.get("total_pages", 0)

    if not total_pages:
        # Count image files
        total_pages = len(list(pages_dir.glob("page-*.jpg")))
        if not total_pages:
            total_pages = len(list(pages_dir.glob("page-*.txt")))

    config = load_config()
    settings = load_settings(pipeline_path, config)
    vision_cfg = settings.get("vision", {})
    max_pages = vision_cfg.get("max_pages_per_call", 20)
    fallback_size = vision_cfg.get("fallback_group_size", 15)
    overlap_pages = vision_cfg.get("overlap_pages", 1)

    # Load triage decisions
    triage = load_triage(pipeline_path)
    skip_pages = get_page_ranges_to_skip(triage, meta, pages_dir)
    if skip_pages:
        print(f"Triage: skipping {len(skip_pages)} pages")

    # Group by chapters or fall back to fixed groups
    toc_chapters = load_toc_chapters(pages_dir)
    if toc_chapters:
        print(f"TOC found: {len(toc_chapters)} chapters")
        chapter_ranges = chapters_to_page_ranges(toc_chapters, total_pages, skip_pages)
        groups = split_large_chapters(chapter_ranges, max_pages)
    else:
        print(f"No TOC found, grouping in batches of {fallback_size} pages")
        groups = fallback_grouping(total_pages, skip_pages, fallback_size)

    # Add overlap between groups
    if overlap_pages > 0:
        groups = add_overlap(groups, overlap_pages)
        print(f"  Added {overlap_pages}-page overlap between chunks")

    # Build manifest
    manifest = []
    for i, group in enumerate(groups):
        chunk_id = f"chunk-{i + 1:04d}"
        image_files = [f"page-{p:04d}.jpg" for p in group["pages"]]
        text_files = [f"page-{p:04d}.txt" for p in group["pages"]]

        # Verify at least some images exist
        existing_images = [f for f in image_files if (pages_dir / f).exists()]

        manifest.append({
            "id": chunk_id,
            "chapter_title": group["title"],
            "pages": group["pages"],
            "image_files": existing_images,
            "text_files": text_files,
            "type": "vision",
        })

    manifest_path = chunks_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    total_pages_covered = sum(len(g["pages"]) for g in groups)
    print(f"Created {len(manifest)} chunks covering {total_pages_covered} pages")
    print(f"  Max pages per chunk: {max(len(g['pages']) for g in groups)}")
    print(f"  Manifest -> {manifest_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/03v_chunk_chapters.py pipeline/<book-name>")
        sys.exit(1)
    run_vision_chunking(sys.argv[1])
