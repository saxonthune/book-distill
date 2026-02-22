# Book Distill

A pipeline that turns PDF books into token-efficient, callable reference material (Claude Code skills, structured markdown). Uses a multi-step assembly line with inspectable intermediate artifacts at each stage.

## Architecture

```
input/*.pdf → 01-pages → 02-triage → 03-chunks → 04-extractions → 05-merged → 06-synthesized → output/
```

Each step reads from the previous step's directory and writes to its own. All intermediate artifacts live in `pipeline/<book-name>/`. Scripts are in `scripts/`, prompt templates in `prompts/`.

## Key Files

- `scripts/config.py` — shared config loader, LiteLLM setup, path helpers
- `scripts/01_extract_text.py` — PDF to per-page text (local, no API)
- `scripts/02_triage.py` — TOC analysis, suggests extract/summarize/skip per chapter (LLM)
- `scripts/03_chunk.py` — pages to sized chunks, respects triage decisions (local)
- `scripts/04_extract.py` — per-chunk YAML extraction, parallel (LLM, cheap model)
- `scripts/05_merge.py` — dedup and merge all extractions (local)
- `scripts/06_synthesize.py` — merged YAML to final SKILL.md (LLM, strong model)
- `prompts/*.md` — prompt templates with `{placeholder}` substitution
- `config.json` — API keys, model choices, chunk sizing (gitignored)

## Common Tasks

### Running a book through the pipeline

1. Place PDF in `input/`
2. Run steps sequentially:
   ```
   .venv/bin/python scripts/01_extract_text.py input/<book>.pdf
   .venv/bin/python scripts/02_triage.py pipeline/<book-name>
   # optionally edit pipeline/<book-name>/02-triage/triage.yaml
   .venv/bin/python scripts/03_chunk.py pipeline/<book-name>
   .venv/bin/python scripts/04_extract.py pipeline/<book-name>
   .venv/bin/python scripts/05_merge.py pipeline/<book-name>
   .venv/bin/python scripts/06_synthesize.py pipeline/<book-name>
   ```
3. Output lands in `output/<book-name>-skill/SKILL.md`

The book name is derived from the PDF filename (lowercased, slugified). Steps 1, 3, and 5 are local (no API calls). Step 4 is resumable — rerun to retry failed chunks.

### Diagnosing and improving output quality

Inspect intermediate artifacts to find where quality drops:
- `01-pages/` — is the PDF text extraction clean? Garbled text here ruins everything downstream.
- `03-chunks/manifest.json` — are chunks the right size? Check word counts.
- `04-extractions/chunk-NNNN.yaml` — spot-check a few. Are the rules/patterns meaningful or generic?
- `05-merged/stats.json` — how much dedup happened? Low dedup may mean chunks are too small.
- `05-merged/merged.yaml` — the full input to synthesis. Is it coherent?
- `06-synthesized/SKILL.md` — the final output.

Common improvements:
- Edit `prompts/extract.md` to get better structured output from extraction
- Edit `prompts/synthesize.md` to change how the final SKILL.md is organized
- Adjust `config.json` chunk sizes if chunks are too small (generic output) or too large (missed detail)
- Change models in `config.json` — upgrade synthesis to `anthropic/claude-sonnet-4` for better editorial quality
- Edit triage YAML to skip more chapters and reduce noise

## Conventions

- All scripts use `click` or plain `sys.argv` — no complex CLI frameworks
- LLM calls go through LiteLLM with `openrouter/` prefix
- YAML is the interchange format between extraction and synthesis steps
- Prompt templates live in `prompts/`, not hardcoded in scripts
