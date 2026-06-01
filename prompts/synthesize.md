Synthesize the following extracted YAML into a SKILL.md for a Claude Code skill.

Rules:
- Prioritize: decision rules > patterns > definitions
- Merge duplicates — if two extractions say the same thing, keep the clearest version
- Resolve contradictions by noting the tension briefly
- Use imperative voice ("Do X when Y", not "The author suggests X")
- Group by theme, not by source chapter
- Each section and heading must appear exactly once. Never repeat a section, restate the document, or emit a second variant of the same content to reach a length target.
- Aim for roughly {target_lines} lines. Prefer covering more of the source material (more distinct rules, patterns, and examples) over compressing aggressively — but add only NEW content, never duplicated content. If you run out of distinct material, stop; a shorter, non-repetitive result is better than a padded one.

Output the full SKILL.md content once, including YAML frontmatter. The frontmatter MUST use this exact format:

```
---
skill: <Skill Name Here>
description: <one-line description>
version: 1.0
author: Claude
tags:
  - <tag>
---
```

The `skill:` key is required — do not use `skill_id:`, `name:`, or other variants.

---

EXTRACTIONS:
{extractions}
