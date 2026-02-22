Synthesize the following extracted YAML into a SKILL.md for a Claude Code skill.

Rules:
- Prioritize: decision rules > patterns > definitions
- Merge duplicates — if two extractions say the same thing, keep the clearest version
- Resolve contradictions by noting the tension briefly
- Use imperative voice ("Do X when Y", not "The author suggests X")
- Group by theme, not by source chapter
- Target: {target_lines} lines max

Output the full SKILL.md content including YAML frontmatter.

---

EXTRACTIONS:
{extractions}
