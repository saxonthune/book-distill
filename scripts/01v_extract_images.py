#!/usr/bin/env python3
"""Step 1v: Extract page images and OCR text from a PDF for the vision pipeline.

Usage:
    python scripts/01v_extract_images.py input/my-book.pdf
    python scripts/01v_extract_images.py input/my-book.pdf --dpi 300 --quality 90

Output:
    pipeline/my-book/01-pages/page-001.jpg   (JPEG page images)
    pipeline/my-book/01-pages/page-001.txt   (OCR text, best-effort)
    pipeline/my-book/01-pages/toc.txt
    pipeline/my-book/01-pages/meta.json
"""

import argparse
import json
import sys
from pathlib import Path

import fitz  # pymupdf

from config import load_config, load_settings, pipeline_dir, ROOT

# Reuse from text extraction script (can't import directly — leading digit in filename)
import importlib
_mod = importlib.import_module("01_extract_text")
slugify = _mod.slugify
pdf_metadata = _mod.pdf_metadata
make_book_name = _mod.make_book_name
extract_toc = _mod.extract_toc
format_toc = _mod.format_toc


def extract_page_images(
    pdf_path: Path,
    pages_dir: Path,
    dpi: int = 200,
    jpeg_quality: int = 85,
) -> tuple[int, int]:
    """Render each PDF page as JPEG and extract OCR text.

    Returns (total_pages, empty_text_count).
    """
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    empty_text = 0

    for i, page in enumerate(doc):
        num = i + 1

        # Render page as JPEG
        pixmap = page.get_pixmap(dpi=dpi)
        jpg_path = pages_dir / f"page-{num:04d}.jpg"
        pixmap.save(str(jpg_path), jpg_quality=jpeg_quality)

        # Also extract text (best-effort, may be garbled)
        text = page.get_text()
        txt_path = pages_dir / f"page-{num:04d}.txt"
        txt_path.write_text(text)
        if not text.strip():
            empty_text += 1

        if num % 50 == 0 or num == total:
            print(f"  {num}/{total} pages rendered", flush=True)

    doc.close()
    return total, empty_text


def extract_pdf_vision(pdf_path: Path, name_override: str | None = None,
                       dpi: int = 200, jpeg_quality: int = 85) -> None:
    """Full vision extraction: page images + OCR text + TOC + metadata."""
    doc = fitz.open(str(pdf_path))

    title, author, first_page_text = pdf_metadata(doc)
    if name_override:
        book_name = slugify(name_override)
    else:
        book_name = make_book_name(title, author)
        if book_name:
            print(f"Using metadata: {author or '?'} — {title}")
        else:
            book_name = slugify(pdf_path.name)

    base = pipeline_dir(book_name)
    pages_dir = base / "01-pages"

    total = len(doc)
    print(f"Extracting {total} pages from {pdf_path.name} [vision: {dpi} DPI, quality {jpeg_quality}]...")

    # Extract TOC
    toc_entries = extract_toc(doc)
    if toc_entries:
        toc_path = pages_dir / "toc.txt"
        toc_path.write_text(format_toc(toc_entries))
        print(f"  TOC extracted ({len(toc_entries)} entries) -> toc.txt")

    doc.close()

    # Extract page images and text
    total, empty_text = extract_page_images(pdf_path, pages_dir, dpi, jpeg_quality)

    meta = {
        "source": str(pdf_path),
        "source_format": "pdf",
        "extraction_method": "vision",
        "book_name": book_name,
        "title": title,
        "author": author,
        "first_page_text": first_page_text,
        "total_pages": total,
        "has_toc": toc_entries is not None,
        "has_images": True,
        "vision_dpi": dpi,
        "vision_jpeg_quality": jpeg_quality,
        "empty_text_pages": empty_text,
    }
    (pages_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"  Metadata -> meta.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract page images from PDF for vision pipeline")
    parser.add_argument("input", help="Path to PDF file")
    parser.add_argument("--name", help="Override book name")
    parser.add_argument("--dpi", type=int, default=None, help="DPI for rendering (default: from config or 200)")
    parser.add_argument("--quality", type=int, default=None, help="JPEG quality 1-100 (default: from config or 85)")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    if input_path.suffix.lower() != ".pdf":
        print(f"Error: Vision pipeline only supports PDF files, got '{input_path.suffix}'")
        sys.exit(1)

    # Load config for vision defaults
    config = load_config()
    vision_cfg = config.get("vision", {})
    dpi = args.dpi or vision_cfg.get("dpi", 200)
    quality = args.quality or vision_cfg.get("jpeg_quality", 85)

    extract_pdf_vision(input_path, args.name, dpi, quality)
