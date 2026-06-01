Synthesize the following extracted YAML into a SKILL.md for a Claude Code skill.

Rules:
- Prioritize by `strength` first, then by type. Most items carry a `strength` field: `must`, `should`, or `consider`. When space is tight, cut from the bottom:
  - **Every `must`-strength rule MUST appear** in the output — these are non-negotiable core rules. Do not drop one to save space.
  - **Include `should`-strength rules** as space allows; prefer them over examples and elaboration.
  - **Include `consider`-strength rules only if room remains** after all must/should rules are covered. These are optional refinements; dropping them is fine and expected.
  - Within a strength tier, prioritize: decision rules > patterns > definitions.
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
