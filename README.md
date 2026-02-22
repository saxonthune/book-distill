# book-distill

Turn PDF books into token-efficient, callable reference material for AI coding assistants.

Takes a book PDF and produces a structured Claude Code skill (SKILL.md + supporting files) through a multi-step pipeline with inspectable intermediate outputs at every stage.

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure API key
cp config.example.json config.json
# Edit config.json — add your OpenRouter API key
```

## Usage

```bash
# 1. Drop a PDF into input/
cp ~/books/my-book.pdf input/

# 2. Extract text from PDF (local, no API)
python scripts/01_extract_text.py input/my-book.pdf

# 3. Triage chapters — suggests extract/summarize/skip (cheap LLM call)
python scripts/02_triage.py pipeline/my-book
# Review and edit pipeline/my-book/02-triage/triage.yaml if desired

# 4. Chunk pages for extraction (local)
python scripts/03_chunk.py pipeline/my-book

# 5. Extract structured YAML from each chunk (parallel, cheap model)
python scripts/04_extract.py pipeline/my-book

# 6. Merge and deduplicate extractions (local)
python scripts/05_merge.py pipeline/my-book

# 7. Synthesize into final SKILL.md (strong model)
python scripts/06_synthesize.py pipeline/my-book
```

Output: `output/my-book-skill/SKILL.md`

## Pipeline

```
input/my-book.pdf
  → 01-pages/       Per-page text extraction
  → 02-triage/      Chapter treatment decisions (extract/summarize/skip)
  → 03-chunks/      Sized text chunks ready for LLM
  → 04-extractions/ Per-chunk structured YAML (principles, patterns, terms)
  → 05-merged/      Deduplicated, combined YAML
  → 06-synthesized/ Final SKILL.md
```

Every intermediate artifact is inspectable. Step 4 is resumable — rerun to retry any failed chunks.

## Configuration

Edit `config.json` to change models, chunk sizes, or synthesis targets. See `config.example.json` for the full schema.

Default models (via OpenRouter):
- **Extraction/triage**: `deepseek/deepseek-chat` (DeepSeek V3.2) — ~$0.25/M input tokens
- **Synthesis**: `deepseek/deepseek-chat` — upgrade to `anthropic/claude-sonnet-4` for better editorial quality

## Cost

A 300-page book typically costs $0.05–0.10 with DeepSeek V3.2 for all steps.

## License

[AGPL-3.0](LICENSE)
