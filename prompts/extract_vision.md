You are reading page images from a book. Extract structured knowledge from what you see.

The images show consecutive pages from: {chapter_context}

Read the text, diagrams, photos, captions, and any visual content directly from the page images. Supplementary OCR text is provided below but may contain errors — trust what you see in the images.

Output ONLY valid YAML matching this schema, no commentary:

```yaml
principles:
  - rule: "Imperative statement of the rule"
    context: "When/where this applies"
    strength: must|should|consider

patterns:
  - name: "Pattern Name"
    when: "Situation description"
    do: "What to do"
    avoid: "What not to do"

anti_patterns:
  - name: "Anti-pattern Name"
    problem: "Why this is bad"
    instead: "What to do instead"

key_terms:
  - term: "Term"
    definition: "Concise definition"
```

Only include items clearly stated or strongly implied. Omit empty sections.
For diagrams and figures: extract the conceptual principle or pattern they illustrate, not a description of the visual.
{extraction_notes}

---

SUPPLEMENTARY OCR TEXT (may contain errors):
{ocr_text}
