You are revising a SKILL.md based on a verification report that found gaps.

Your job: fix the identified issues while preserving everything that's already good.

CURRENT SKILL.md:
{skill}

---

VERIFICATION REPORT:
{report}

---

SOURCE MATERIAL (merged.yaml):
{merged}

---

Instructions:
- This revision is ADDITIVE. Preserve the current SKILL.md essentially verbatim and weave in the flagged gaps. The report has already been filtered to high-priority gaps (must/should-strength rules and load-bearing concepts) — treat every listed item as worth adding.
- Address every item listed under "Missing Items" — integrate each into the appropriate existing section (or add a short new subsection if none fits)
- Fix every item listed under "Diluted Items" — restore the nuance from the source material
- Remove or replace anything flagged under "Generic Filler" with real content from the source
- Do NOT drop, shorten, or merge away any existing unflagged content to make room. The document is EXPECTED to grow. You may go up to {target_lines} lines — this budget already includes headroom for the additions.
- Maintain the same structure, voice (imperative), and YAML frontmatter format
- Group by theme, not by source chapter
- Merge only true duplicates; resolve contradictions briefly

Output the complete revised SKILL.md, including the YAML frontmatter.
