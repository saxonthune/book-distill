# Book Distill

A pipeline that turns PDF books into token-efficient, callable reference material (Claude Code skills, structured markdown). Uses a multi-step assembly line with inspectable intermediate artifacts at each stage.

## Architecture

```
Text pipeline:
input/*.pdf → 01-pages → 01b-settings → 02-triage → 03-chunks → 04-extractions → 05-merged → 06-synthesized → 07-verified → 08-revise → output/
                                                                                                                                  ↘ 09-install → ~/.claude/skills/
Vision pipeline (scanned/image-heavy books):
input/*.pdf → 01v-pages → 01b-settings → 02-triage → 03v-chunks → 04v-extractions → 05-merged → 06-synthesized → ... → output/
```

Each step reads from the previous step's directory and writes to its own. All intermediate artifacts live in `pipeline/<book-name>/`. Scripts are in `scripts/`, prompt templates in `prompts/`.

## Key Files

- `scripts/config.py` — shared config loader, LiteLLM setup, path helpers, `load_settings()` for per-book overrides
- `scripts/01_extract_text.py` — PDF to per-page text (local, no API); `--markdown` for pymupdf4llm extraction
- `scripts/01b_settings.py` — compute chunk/synthesis settings from source length; `--ai` for LLM-assisted tuning
- `scripts/02_triage.py` — TOC analysis, suggests extract/summarize/skip per chapter (LLM)
- `scripts/03_chunk.py` — pages to sized chunks, respects triage decisions (local)
- `scripts/01v_extract_images.py` — PDF to per-page JPEG images + OCR text (local, no API); vision pipeline
- `scripts/03v_chunk_chapters.py` — pages to chapter-based chunks using TOC (local); vision pipeline
- `scripts/04v_extract.py` — per-chunk vision extraction with page images, parallel (LLM, vision model)
- `scripts/04_extract.py` — per-chunk YAML extraction, parallel (LLM, cheap model)
- `scripts/05_merge.py` — dedup and merge all extractions (local)
- `scripts/06_synthesize.py` — merged YAML to final SKILL.md (LLM, strong model)
- `scripts/07_verify.py` — coverage check of SKILL.md against merged.yaml (LLM, cheap model)
- `scripts/08_revise.py` — verify→revise loop, feeds gaps back into re-synthesis (LLM)
- `scripts/09_install.py` — install best SKILL.md into `~/.claude/skills/book-summary/<file>.md` and update routing table (local)
- `pipeline/<book>/book-meta.json` — author, title, year, summary, filename for install/routing
- `scripts/reset.py` — delete pipeline artifacts from a given step onward (`--from 03`)
- `prompts/*.md` — prompt templates with `{placeholder}` substitution
- `config.json` — API keys, model choices, chunk sizing (gitignored)

## Common Tasks

### Running a book through the pipeline

1. Place PDF in `input/`
2. Prepare the source (choose based on the PDF):
   - **Default**: no prep needed, plain text extraction works for most books
   - **Scanned PDFs** (no selectable text): OCR first with `ocrmypdf --skip-text --output-type pdf input/<book>.pdf input/<book>-ocr.pdf`
   - **Equation-heavy PDFs**: use `--markdown` flag for better equation/formatting preservation (uses pymupdf4llm)
   - Inspect `01-pages/` after extraction — if text is garbled, try a different method. Cleanup before proceeding is fine.
3. Run steps sequentially:
   ```
   .venv/bin/python scripts/01_extract_text.py input/<book>.pdf  # add --markdown for equations
   .venv/bin/python scripts/01b_settings.py pipeline/<book-name>  # optional: add --ai
   .venv/bin/python scripts/02_triage.py pipeline/<book-name>
   # optionally edit pipeline/<book-name>/02-triage/triage.yaml
   .venv/bin/python scripts/03_chunk.py pipeline/<book-name>
   .venv/bin/python scripts/04_extract.py pipeline/<book-name>
   .venv/bin/python scripts/05_merge.py pipeline/<book-name>
   .venv/bin/python scripts/06_synthesize.py pipeline/<book-name>
   .venv/bin/python scripts/07_verify.py pipeline/<book-name>
   .venv/bin/python scripts/08_revise.py pipeline/<book-name>
   .venv/bin/python scripts/09_install.py pipeline/<book-name>
   ```
4. Output lands in `output/<book-name>-skill/SKILL.md` and `~/.claude/skills/book-summary/<file>.md`

The book name is derived from the PDF filename (lowercased, slugified). Steps 1, 1b, 3, and 5 are local (no API calls). Step 1b is optional — without it, config.json defaults are used. Step 4 is resumable — rerun to retry failed chunks. Step 9 requires `book-meta.json` in the pipeline dir (author, title, year, summary, filename) — it will prompt interactively if missing.

All books install into a single shared skill at `~/.claude/skills/book-summary/`. The `SKILL.md` there is a routing table; each book is a separate `.md` file. The skill triggers when the user references an author or title, and routes to the correct book file.

### Vision pipeline (scanned/image-heavy books)

Use this when: OCR text is garbled, the book has important images/diagrams/photos, or text extraction fails. Sends page images directly to a vision-capable LLM. Pages are grouped by chapter (using TOC) so cross-page references are preserved.

```
.venv/bin/python scripts/01v_extract_images.py input/<book>.pdf  # add --dpi 300 for small print
.venv/bin/python scripts/01b_settings.py pipeline/<book-name>    # optional
.venv/bin/python scripts/02_triage.py pipeline/<book-name>       # unchanged
.venv/bin/python scripts/03v_chunk_chapters.py pipeline/<book-name>
.venv/bin/python scripts/04v_extract.py pipeline/<book-name>
.venv/bin/python scripts/05_merge.py pipeline/<book-name>        # unchanged from here on
.venv/bin/python scripts/06_synthesize.py pipeline/<book-name>
.venv/bin/python scripts/07_verify.py pipeline/<book-name>
.venv/bin/python scripts/08_revise.py pipeline/<book-name>
.venv/bin/python scripts/09_install.py pipeline/<book-name>
```

Steps 01v and 03v replace steps 01 and 03. Step 04v replaces step 04. Steps 05-09 are shared — they consume the same YAML extraction format. The vision model is set via `models.vision_extraction` in `config.json`. Image quality/chunking is configured in the `vision` block (dpi, jpeg_quality, max_pages_per_call, fallback_group_size, max_workers).

### Diagnosing and improving output quality

Inspect intermediate artifacts to find where quality drops:
- `01-pages/` — is the PDF text extraction clean? Garbled text here ruins everything downstream. If pages are empty, the PDF is likely scanned and needs OCR first (see above).
- `03-chunks/manifest.json` — are chunks the right size? Check word counts.
- `04-extractions/chunk-NNNN.yaml` — spot-check a few. Are the rules/patterns meaningful or generic?
- `05-merged/stats.json` — how much dedup happened? Low dedup may mean chunks are too small.
- `05-merged/merged.yaml` — the full input to synthesis. Is it coherent?
- `06-synthesized/SKILL.md` — the final output.
- `07-verified/report.md` — coverage audit: missing items, diluted items, verdict.

**After step 07 (verify), do NOT automatically run step 08 (revise).** Instead, summarize the verification gaps for the user — many "missing" items are noise (obscure terms, specific building names, minor examples). Let the user decide whether revision is worth the cost, and which gaps to address.

Common improvements:
- Edit `prompts/extract.md` to get better structured output from extraction
- Edit `prompts/synthesize.md` to change how the final SKILL.md is organized
- Run `01b_settings.py --ai` to get LLM-recommended settings for the specific source
- Edit `pipeline/<book>/settings.json` to override chunk sizes and target lines per-book
- Adjust `config.json` chunk sizes as global defaults if chunks are too small (generic output) or too large (missed detail)
- Change models in `config.json` — upgrade synthesis to `anthropic/claude-sonnet-4` for better editorial quality
- Edit triage YAML to skip more chapters and reduce noise
- Add `extraction_notes` to `pipeline/<book>/settings.json` for per-book extraction guidance (see below)

### Customizing extraction per book

**Before running step 04 (extraction), always ask the user once** what they want from the book. Give them context to decide — read the first page of extracted text and share what you know about the book (title, author, subject, what it's known for). Don't search the web; use what you can infer from the PDF metadata and text plus your own knowledge.

Then ask:
- Do you want to emphasize particular aspects? (practical techniques, theoretical foundations, decision frameworks, critique, etc.)
- For math-heavy sources: should equations be preserved or explained conceptually?
- Anything to de-emphasize? (historical context, proofs, examples, etc.)

If the user says "just run it" or has no preferences, that's fine — skip `extraction_notes` and use the default prompt.

Otherwise, add an `extraction_notes` field to `pipeline/<book>/settings.json`. This gets injected into every extraction prompt.

Example `extraction_notes` values:
- `"Focus on practical design patterns and decision rules. De-emphasize historical context."`
- `"This source has many equations mangled by PDF extraction. Reconstruct key formulas in readable form (e.g., H = -sum(p_i * log(p_i))). For routine derivations, explain what the math establishes."`
- `"Emphasize the author's critique of existing approaches and the proposed alternatives."`

## Conventions

- All scripts use `click` or plain `sys.argv` — no complex CLI frameworks
- LLM calls go through LiteLLM with `openrouter/` prefix
- YAML is the interchange format between extraction and synthesis steps
- Prompt templates live in `prompts/`, not hardcoded in scripts
