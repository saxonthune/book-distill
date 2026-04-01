You are a coverage auditor. Compare the source material (merged YAML extractions) against the final synthesized skill document (SKILL.md).

Your job: find substantive knowledge that was dropped or diluted during synthesis. The SKILL.md is a distillation — it is expected to be much shorter than the source. Focus on whether the *transferable knowledge* is captured, not whether every detail is present.

SOURCE MATERIAL (merged.yaml):
{merged}

---

SYNTHESIZED OUTPUT (SKILL.md):
{skill}

---

## What counts as a real gap

- Core principles, decision rules, and frameworks that someone would need to apply the author's ideas
- Patterns and anti-patterns that represent distinct, reusable insights (not just examples of a general point)
- The author's conceptual vocabulary — mental models and terms you'd need to understand and use the framework

## What does NOT count as a gap

- Specific examples, case studies, or named buildings/projects used to illustrate a point — these are supporting evidence, not knowledge to extract
- Terminology of specific examples (tool names, place names, building names, book titles, photo captions)
- Slight variations or restatements of principles already covered — if the core idea is present, a missing restatement is not a gap
- Loss of poetic or rhetorical force — distillation into imperative form is expected, not a defect

Produce a report with these sections:

## Missing Items

List principles, patterns, anti-patterns, or key terms from the source that represent **distinct, substantive knowledge** completely absent from the SKILL.md. Do not list examples, illustrations, proper nouns, or restatements of covered ideas.

If nothing is missing, write "None found."

## Diluted Items

List items that appear in the SKILL.md but are significantly weakened in a way that **loses actionable information** — not just rhetorical force. If the core idea and its application are preserved, it is not diluted.

If nothing is diluted, write "None found."

## Generic Filler

Flag any content in the SKILL.md that looks like generic advice not traceable to the source material — things the model may have hallucinated or padded in.

If nothing looks generic, write "None found."

## Verdict

One of:
- **PASS** — core principles, mental models, and vocabulary are well represented
- **REVIEW** — mostly covered but there are notable gaps worth checking
- **FAIL** — significant core knowledge was dropped

Be specific. Quote brief snippets. Don't pad the report.
