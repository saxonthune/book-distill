Synthesize the following extracted YAML into a SKILL.md for a Claude Code skill.

Rules:
- Prioritize: decision rules > patterns > definitions
- Merge duplicates — if two extractions say the same thing, keep the clearest version
- Resolve contradictions by noting the tension briefly
- Use imperative voice ("Do X when Y", not "The author suggests X")
- Group by theme, not by source chapter
- Target: {target_lines} lines max

Output the full SKILL.md content including YAML frontmatter. The frontmatter MUST use this exact format:

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
