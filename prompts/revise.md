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
- Address every item listed under "Missing Items" — integrate them into the appropriate section
- Fix every item listed under "Diluted Items" — restore the nuance from the source material
- Remove or replace anything flagged under "Generic Filler" with real content from the source
- Keep all existing content that was NOT flagged — do not drop good material
- Stay within {target_lines} lines
- Maintain the same structure, voice (imperative), and YAML frontmatter format
- Group by theme, not by source chapter
- Merge duplicates, resolve contradictions briefly

Output the complete revised SKILL.md, including the YAML frontmatter.
