"""Shared config loader for all pipeline scripts."""

import json
import os
import sys
from pathlib import Path

import litellm

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
PROMPTS_DIR = ROOT / "prompts"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"Error: {CONFIG_PATH} not found.")
        print(f"Copy config.example.json to config.json and add your API key.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_api_key(config: dict) -> str:
    key = config.get("openrouter_api_key", "")
    if not key or key.startswith("sk-or-v1-your"):
        print("Error: Set your OpenRouter API key in config.json")
        sys.exit(1)
    return key


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text()


def setup_litellm(config: dict):
    """Configure LiteLLM to use OpenRouter."""
    os.environ["OPENROUTER_API_KEY"] = get_api_key(config)


def load_settings(pipeline_path: Path, config: dict) -> dict:
    """Load pipeline settings: settings.json overrides, config.json fallback."""
    settings_path = Path(pipeline_path) / "settings.json"
    vision_defaults = {
        "dpi": 200, "jpeg_quality": 85, "max_pages_per_call": 20,
        "fallback_group_size": 20, "overlap_pages": 1, "max_workers": 4,
    }
    if settings_path.exists():
        with open(settings_path) as f:
            settings = json.load(f)
        # Merge: settings.json values override config.json
        chunking = config.get("chunking", {}).copy()
        chunking.update(settings.get("chunking", {}))
        synthesis = config.get("synthesis", {}).copy()
        synthesis.update(settings.get("synthesis", {}))
        vision = config.get("vision", vision_defaults).copy()
        vision.update(settings.get("vision", {}))
        result = {"chunking": chunking, "synthesis": synthesis, "vision": vision}
        if "extraction_notes" in settings:
            result["extraction_notes"] = settings["extraction_notes"]
        return result
    # No settings.json — use config.json as-is
    return {
        "chunking": config.get("chunking", {"max_words": 500, "overlap_words": 50}),
        "synthesis": config.get("synthesis", {"target_lines": 400}),
        "vision": config.get("vision", vision_defaults),
    }


def stream_completion(model: str, messages: list, label: str = "Generating", quiet: bool = False) -> tuple[str, dict]:
    """Stream a litellm completion, printing a progress line with token count.

    Returns (content, usage_dict) where usage_dict has input_tokens/output_tokens.
    """
    import time
    start = time.time()
    chunks = []
    token_count = 0

    response = litellm.completion(
        model=f"openrouter/{model}",
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    last_chunk = None
    last_update = start
    for chunk in response:
        last_chunk = chunk
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            chunks.append(delta.content)
            token_count += 1
            now = time.time()
            if not quiet and now - last_update >= 15:
                last_update = now
                print(f"  {label}... {token_count} chunks, {now - start:.0f}s", flush=True)

    elapsed = time.time() - start
    if not quiet:
        print(f"  {label}... done, {elapsed:.0f}s", flush=True)

    content = "".join(chunks)

    # Usage from streaming — providers may include it on the last chunk
    usage_dict = {"input_tokens": 0, "output_tokens": 0}
    if last_chunk and hasattr(last_chunk, "usage") and last_chunk.usage:
        usage_dict["input_tokens"] = getattr(last_chunk.usage, "prompt_tokens", 0) or 0
        usage_dict["output_tokens"] = getattr(last_chunk.usage, "completion_tokens", 0) or 0

    return content, usage_dict


def pipeline_dir(book_name: str) -> Path:
    """Return the pipeline directory for a book, creating subdirs as needed."""
    base = ROOT / "pipeline" / book_name
    for step in ["01-pages", "02-triage", "03-chunks", "04-extractions", "05-merged", "06-synthesized", "07-verified"]:
        (base / step).mkdir(parents=True, exist_ok=True)
    return base
