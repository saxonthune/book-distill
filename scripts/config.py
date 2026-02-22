"""Shared config loader for all pipeline scripts."""

import json
import os
import sys
from pathlib import Path

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


def pipeline_dir(book_name: str) -> Path:
    """Return the pipeline directory for a book, creating subdirs as needed."""
    base = ROOT / "pipeline" / book_name
    for step in ["01-pages", "02-triage", "03-chunks", "04-extractions", "05-merged", "06-synthesized"]:
        (base / step).mkdir(parents=True, exist_ok=True)
    return base
