#!/usr/bin/env python3
"""Step 1: Extract text from a PDF or EPUB into per-page/chapter text files.

Usage:
    python scripts/01_extract_text.py input/my-book.pdf
    python scripts/01_extract_text.py input/my-book.epub

Output:
    pipeline/my-book/01-pages/page-001.txt   (PDF)
    pipeline/my-book/01-pages/ch-001.txt     (EPUB)
    pipeline/my-book/01-pages/toc.txt
    pipeline/my-book/01-pages/meta.json
"""

import json
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

import fitz  # pymupdf

from config import ROOT, pipeline_dir


def slugify(name: str) -> str:
    """Turn a filename into a clean directory name."""
    name = Path(name).stem  # drop extension
    name = re.sub(r"[^\w\s-]", "", name.lower())
    name = re.sub(r"[\s_]+", "-", name.strip())
    return name


# --- HTML to text ---

class HTMLTextExtractor(HTMLParser):
    """Strip HTML tags, preserve paragraph breaks."""

    def __init__(self):
        super().__init__()
        self._pieces = []
        self._block_tags = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                            "li", "blockquote", "tr", "br", "hr"}
        self._in_tag = None

    def handle_starttag(self, tag, attrs):
        if tag in self._block_tags:
            self._pieces.append("\n")

    def handle_endtag(self, tag):
        if tag in self._block_tags:
            self._pieces.append("\n")

    def handle_data(self, data):
        self._pieces.append(data)

    def get_text(self) -> str:
        text = "".join(self._pieces)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html: str) -> str:
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


# --- EPUB extraction ---

def epub_metadata(epub_path: Path) -> tuple[str | None, str | None]:
    """Extract dc:title and dc:creator from EPUB metadata."""
    try:
        with zipfile.ZipFile(epub_path) as zf:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            opf_path = container.find(".//c:rootfile", ns).attrib["full-path"]
            opf = ET.fromstring(zf.read(opf_path))
            dc_ns = {"dc": "http://purl.org/dc/elements/1.1/"}
            title_el = opf.find(".//dc:title", dc_ns)
            creator_el = opf.find(".//dc:creator", dc_ns)
            title = title_el.text.strip() if title_el is not None and title_el.text else None
            creator = creator_el.text.strip() if creator_el is not None and creator_el.text else None
            return title, creator
    except Exception:
        return None, None


def make_book_name(title: str | None, creator: str | None, max_title_words: int = 4) -> str | None:
    """Build a short book name from author last name + first few title words."""
    if not title:
        return None
    # Take first N words from title, dropping subtitles (after : or .)
    short_title = re.split(r"[:.!?—]", title)[0].strip()
    title_words = short_title.split()[:max_title_words]
    title_part = " ".join(title_words)

    # Extract last name from creator
    if creator:
        # Handle "First Last", "First M. Last", "Last, First"
        if "," in creator:
            last_name = creator.split(",")[0].strip()
        else:
            last_name = creator.split()[-1].strip()
        return slugify(f"{last_name} {title_part}")

    return slugify(title_part)


def extract_epub(epub_path: Path, name_override: str | None = None) -> None:
    # Derive book name: override > metadata (author + title) > filename
    if name_override:
        book_name = slugify(name_override)
    else:
        title, creator = epub_metadata(epub_path)
        book_name = make_book_name(title, creator)
        if book_name:
            print(f"Using metadata: {creator or '?'} — {title}")
        else:
            book_name = slugify(epub_path.name)
    base = pipeline_dir(book_name)
    pages_dir = base / "01-pages"

    with zipfile.ZipFile(epub_path) as zf:
        # Parse container.xml to find the OPF file
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        opf_path = container.find(".//c:rootfile", ns).attrib["full-path"]
        opf_dir = str(Path(opf_path).parent)
        if opf_dir == ".":
            opf_dir = ""

        # Parse OPF to get spine order and metadata
        opf = ET.fromstring(zf.read(opf_path))
        opf_ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}

        # Build id → href map from manifest
        manifest = {}
        for item in opf.findall(".//opf:manifest/opf:item", opf_ns):
            item_id = item.attrib["id"]
            href = item.attrib["href"]
            media = item.attrib.get("media-type", "")
            if "html" in media or "xhtml" in media:
                manifest[item_id] = href

        # Get spine order
        spine_ids = []
        for itemref in opf.findall(".//opf:spine/opf:itemref", opf_ns):
            idref = itemref.attrib["idref"]
            if idref in manifest:
                spine_ids.append(idref)

        # Extract NCX TOC if available
        toc_entries = extract_epub_toc(zf, opf, opf_ns, opf_dir)
        if toc_entries:
            toc_path = pages_dir / "toc.txt"
            toc_path.write_text(format_toc(toc_entries))
            print(f"  TOC extracted ({len(toc_entries)} entries) → toc.txt")

        # Extract chapters in spine order
        total = len(spine_ids)
        empty_count = 0
        print(f"Extracting {total} chapters from {epub_path.name}...")

        for i, item_id in enumerate(spine_ids):
            href = manifest[item_id]
            full_path = f"{opf_dir}/{href}" if opf_dir else href
            try:
                html = zf.read(full_path).decode("utf-8", errors="replace")
            except KeyError:
                # Some EPUBs have URL-encoded paths
                from urllib.parse import unquote
                full_path = unquote(full_path)
                try:
                    html = zf.read(full_path).decode("utf-8", errors="replace")
                except KeyError:
                    empty_count += 1
                    continue

            text = html_to_text(html)
            ch_file = pages_dir / f"ch-{i + 1:04d}.txt"
            ch_file.write_text(text)
            if not text.strip():
                empty_count += 1

        print(f"  {total} chapters → {pages_dir}/")
        if empty_count:
            print(f"  ({empty_count} empty chapters — likely cover/images)")

    meta = {
        "source": str(epub_path),
        "source_format": "epub",
        "book_name": book_name,
        "total_pages": total,
        "empty_pages": empty_count,
        "has_toc": toc_entries is not None,
    }
    (pages_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"  Metadata → meta.json")


def extract_epub_toc(zf: zipfile.ZipFile, opf: ET.Element, opf_ns: dict, opf_dir: str) -> list[dict] | None:
    """Extract TOC from NCX or nav document."""
    # Try NCX first (EPUB 2)
    for item in opf.findall(".//opf:manifest/opf:item", opf_ns):
        media = item.attrib.get("media-type", "")
        if "ncx" in media:
            href = item.attrib["href"]
            full_path = f"{opf_dir}/{href}" if opf_dir else href
            try:
                ncx = ET.fromstring(zf.read(full_path))
                return parse_ncx_toc(ncx)
            except (KeyError, ET.ParseError):
                pass

    # Try nav document (EPUB 3)
    for item in opf.findall(".//opf:manifest/opf:item", opf_ns):
        props = item.attrib.get("properties", "")
        if "nav" in props:
            href = item.attrib["href"]
            full_path = f"{opf_dir}/{href}" if opf_dir else href
            try:
                nav_html = zf.read(full_path).decode("utf-8", errors="replace")
                return parse_nav_toc(nav_html)
            except KeyError:
                pass

    return None


def parse_ncx_toc(ncx: ET.Element, level: int = 1) -> list[dict]:
    """Parse NCX navMap into TOC entries."""
    ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
    entries = []

    nav_points = ncx.findall(".//ncx:navMap/ncx:navPoint", ns) if level == 1 else []
    if not nav_points:
        # Try without namespace
        nav_points = ncx.findall(".//{http://www.daisy.org/z3986/2005/ncx/}navPoint")

    for np in nav_points:
        label_el = np.find("ncx:navLabel/ncx:text", ns)
        if label_el is None:
            label_el = np.find(".//{http://www.daisy.org/z3986/2005/ncx/}text")
        title = label_el.text.strip() if label_el is not None and label_el.text else "Untitled"
        entries.append({"level": 1, "title": title, "page": len(entries) + 1})

    return entries if entries else None


def parse_nav_toc(nav_html: str) -> list[dict]:
    """Parse EPUB 3 nav document for TOC entries."""
    # Simple regex extraction — nav docs are well-structured
    entries = []
    for match in re.finditer(r"<a[^>]*>([^<]+)</a>", nav_html):
        title = match.group(1).strip()
        if title:
            entries.append({"level": 1, "title": title, "page": len(entries) + 1})
    return entries if entries else None


# --- PDF extraction ---

def extract_toc(doc: fitz.Document) -> list[dict] | None:
    """Extract table of contents if available."""
    toc = doc.get_toc()
    if not toc:
        return None
    entries = []
    for level, title, page_num in toc:
        entries.append({"level": level, "title": title, "page": page_num})
    return entries


def extract_pdf(pdf_path: Path, name_override: str | None = None) -> None:
    book_name = slugify(name_override) if name_override else slugify(pdf_path.name)
    base = pipeline_dir(book_name)
    pages_dir = base / "01-pages"

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    print(f"Extracting {total} pages from {pdf_path.name}...")

    # Extract TOC
    toc_entries = extract_toc(doc)
    if toc_entries:
        toc_path = pages_dir / "toc.txt"
        toc_path.write_text(format_toc(toc_entries))
        print(f"  TOC extracted ({len(toc_entries)} entries) → toc.txt")

    # Extract pages
    empty_count = 0
    for i, page in enumerate(doc):
        text = page.get_text()
        page_file = pages_dir / f"page-{i + 1:04d}.txt"
        page_file.write_text(text)
        if not text.strip():
            empty_count += 1

    doc.close()

    print(f"  {total} pages → {pages_dir}/")
    if empty_count:
        print(f"  ({empty_count} empty pages — likely images/diagrams)")

    meta = {
        "source": str(pdf_path),
        "source_format": "pdf",
        "book_name": book_name,
        "total_pages": total,
        "empty_pages": empty_count,
        "has_toc": toc_entries is not None,
    }
    (pages_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"  Metadata → meta.json")


# --- Shared ---

def format_toc(entries: list[dict]) -> str:
    """Format TOC entries as readable text."""
    lines = []
    for e in entries:
        indent = "  " * (e["level"] - 1)
        lines.append(f"{indent}{e['title']} (p.{e['page']})")
    return "\n".join(lines)


# --- Main ---

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python scripts/01_extract_text.py <path-to-pdf-or-epub> [--name <skill-name>]")
        sys.exit(1)

    input_path = Path(sys.argv[1]).resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    # Optional --name override
    name_override = None
    if len(sys.argv) == 4 and sys.argv[2] == "--name":
        name_override = sys.argv[3]
    elif len(sys.argv) == 3:
        # Allow positional: script.py file.epub "My Book Name"
        name_override = sys.argv[2]

    suffix = input_path.suffix.lower()
    if suffix == ".epub":
        extract_epub(input_path, name_override)
    elif suffix == ".pdf":
        extract_pdf(input_path, name_override)
    else:
        print(f"Error: Unsupported format '{suffix}'. Use .pdf or .epub")
        sys.exit(1)
