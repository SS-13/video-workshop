# Local Personalization Protocol

Use this protocol after a clean clone when the user wants the system to learn
from existing local content. The source material stays local and ignored by Git.

## Inputs

Read all available user-approved text sources, usually:

```text
01_inbox/**/*.md
02_scripts/**/*.md
06_logs/**/*.md
```

The user may provide additional local paths. Do not read credentials, browser
profiles, cookies, private keys, or unrelated personal folders.

## Outputs

Write only these local, ignored artifacts:

```text
10_skills/personal-speaking-style/SKILL.md
11_templates/关键词收集/字幕纠错词库.tsv
11_templates/关键词收集/专有名词清单.md
00_state/personalization.json
```

## Method

1. Keep source files unchanged.
2. Compare raw ideas with reviewed scripts when both exist.
3. Extract stable patterns only: sentence rhythm, preferred transitions,
   repeated structures, phrases to keep, phrases to avoid, and correction pairs.
4. Separate style from subject matter. Do not treat one topic as a permanent
   personality rule.
5. Add a small number of source references, not copied personal passages.
6. Set `00_state/personalization.json.status` to `ready` only after the local
   profile and vocabulary files have been reviewed for accidental secrets.

## Continuous Learning

Do not silently rewrite the profile after every video. Record corrections as
Observations. The Daily Engineering Loop deduplicates them and selects at most
three TopK candidates per day. Formal rules change only through an explicit,
reviewed implementation step.
