You are analyzing a book's table of contents to decide how to process each chapter.

For each chapter, assign a treatment:
- **extract**: Core theory, principles, decision rules — full extraction
- **summarize**: Worked examples, reference material — extract pattern names + brief summary only
- **skip**: Intros, conclusions, anecdotes, case studies — skip entirely

Output ONLY valid YAML:

```yaml
chapters:
  - number: 1
    title: "Chapter Title"
    treatment: extract|summarize|skip
    reason: "Brief justification"
```

---

TABLE OF CONTENTS:
{toc}
