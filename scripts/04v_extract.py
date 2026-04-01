#!/usr/bin/env python3
"""Step 4v: Run vision LLM extraction on chapter chunks (parallel).

Sends page images + supplementary OCR text to a vision-capable model.

Usage:
    python scripts/04v_extract.py pipeline/my-book

Output:
    pipeline/<book>/04-extractions/chunk-0001.yaml
    pipeline/<book>/04-extractions/chunk-0002.yaml
    ...
    pipeline/<book>/04-extractions/summary.json
"""

import base64
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import litellm
import yaml

from config import load_config, load_settings, setup_litellm, load_prompt


def load_image_base64(image_path: Path) -> str:
    """Read a JPEG file and return its base64-encoded string."""
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def build_vision_messages(
    prompt: str,
    image_paths: list[Path],
    text_paths: list[Path],
    chapter_title: str | None = None,
) -> list[dict]:
    """Build the messages array for a vision LLM call.

    Returns a single user message with text prompt + OCR supplement + page images.
    """
    # Gather OCR text as supplement
    ocr_parts = []
    for tp in text_paths:
        if tp.exists():
            text = tp.read_text().strip()
            if text:
                page_num = tp.stem.split("-")[1]
                ocr_parts.append(f"[Page {int(page_num)}]\n{text}")

    ocr_text = "\n\n".join(ocr_parts) if ocr_parts else "(no OCR text available)"
    chapter_context = chapter_title or "unknown section"

    # Fill prompt template
    filled_prompt = (prompt
                     .replace("{chapter_context}", chapter_context)
                     .replace("{ocr_text}", ocr_text))

    # Build multimodal content: text first, then images
    content = [{"type": "text", "text": filled_prompt}]

    for img_path in image_paths:
        if img_path.exists():
            b64 = load_image_base64(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

    return [{"role": "user", "content": content}]


def extract_chunk_vision(
    model: str,
    prompt_template: str,
    chunk: dict,
    pages_dir: Path,
    provider_prefs: dict | None = None,
) -> dict:
    """Extract structured YAML from a single vision chunk."""
    image_paths = [pages_dir / f for f in chunk["image_files"]]
    text_paths = [pages_dir / f for f in chunk["text_files"]]

    messages = build_vision_messages(
        prompt_template, image_paths, text_paths, chunk.get("chapter_title"),
    )

    extra_body = {}
    if provider_prefs:
        extra_body["provider"] = provider_prefs

    response = litellm.completion(
        model=f"openrouter/{model}",
        messages=messages,
        max_tokens=32000,
        **( {"extra_body": extra_body} if extra_body else {}),
    )

    raw = response.choices[0].message.content or ""

    # Extract YAML from response
    yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", raw, re.DOTALL)
    yaml_text = yaml_match.group(1) if yaml_match else raw

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        data = {"_parse_error": True, "_raw": raw}

    usage = response.usage
    return {
        "chunk": chunk["id"],
        "data": data,
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
    }


def run_vision_extraction(pipeline_path: str) -> None:
    pipeline_path = Path(pipeline_path).resolve()
    pages_dir = pipeline_path / "01-pages"
    chunks_dir = pipeline_path / "03-chunks"
    extract_dir = pipeline_path / "04-extractions"
    extract_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = chunks_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: {manifest_path} not found. Run 03v_chunk_chapters.py first.")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())

    # Verify this is a vision manifest
    if manifest and not manifest[0].get("type") == "vision":
        print("Error: Manifest is not from vision pipeline. Run 03v_chunk_chapters.py first.")
        sys.exit(1)

    # Skip already-processed chunks
    done = {p.stem for p in extract_dir.glob("chunk-*.yaml")}
    remaining = [c for c in manifest if c["id"] not in done]

    if done:
        print(f"Resuming: {len(done)} already done, {len(remaining)} remaining")

    if not remaining:
        print("All chunks already extracted.")
        return

    config = load_config()
    setup_litellm(config)
    model = config["models"]["vision_extraction"]
    settings = load_settings(pipeline_path, config)
    vision_cfg = settings.get("vision", {})
    max_workers = vision_cfg.get("max_workers", 2)
    extraction_notes = settings.get("extraction_notes", "")
    provider_prefs = vision_cfg.get("provider", None)
    prompt_template = load_prompt("extract_vision").replace("{extraction_notes}", extraction_notes)

    total_count = len(remaining)
    total_images = sum(len(c["image_files"]) for c in remaining)
    print(f"Extracting {total_count} chunks ({total_images} page images) with {model}...", flush=True)
    if provider_prefs:
        print(f"  Provider preferences: {provider_prefs}", flush=True)

    total_in = 0
    total_out = 0
    errors = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(extract_chunk_vision, model, prompt_template, chunk, pages_dir, provider_prefs): chunk
            for chunk in remaining
        }

        for i, future in enumerate(as_completed(futures), 1):
            chunk = futures[future]
            pct = i * 100 // total_count
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total_count - i) / rate if rate > 0 else 0
            try:
                result = future.result()

                out_path = extract_dir / f"{chunk['id']}.yaml"
                out_path.write_text(yaml.dump(
                    result["data"], default_flow_style=False,
                    sort_keys=False, allow_unicode=True,
                ))

                total_in += result["input_tokens"]
                total_out += result["output_tokens"]

                if result["data"] and result["data"].get("_parse_error"):
                    errors += 1
                    print(f"  [{i}/{total_count} {pct}%] {chunk['id']} ({chunk.get('chapter_title', '?')}) — YAML parse error  ETA {eta:.0f}s", flush=True)
                else:
                    n_pages = len(chunk["image_files"])
                    print(f"  [{i}/{total_count} {pct}%] {chunk['id']} ({n_pages}pp, {chunk.get('chapter_title', '?')}) — ok  ETA {eta:.0f}s", flush=True)

            except Exception as e:
                errors += 1
                print(f"  [{i}/{total_count} {pct}%] {chunk['id']} — ERROR: {e}", flush=True)

    elapsed = time.time() - start

    summary = {
        "model": model,
        "pipeline": "vision",
        "total_chunks": len(manifest),
        "extracted": len(remaining) - errors,
        "errors": errors,
        "total_images": total_images,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "elapsed_seconds": round(elapsed, 1),
    }
    (extract_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nDone in {elapsed:.0f}s")
    print(f"  Tokens: {total_in:,} in / {total_out:,} out")
    if errors:
        print(f"  {errors} errors — rerun to retry failed chunks")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/04v_extract.py pipeline/<book-name>")
        sys.exit(1)
    run_vision_extraction(sys.argv[1])
