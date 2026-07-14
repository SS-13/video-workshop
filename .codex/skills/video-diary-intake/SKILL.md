---
name: video-diary-intake
description: Video diary idea intake for Video Workshop. Use when the user says to start today's video diary, record a raw thought, add a topic, or initialize a date workspace. Preserve raw wording in 01_inbox, create date folders, and do not generate scripts unless explicitly requested.
---

# Video Diary Intake

## Core Rule

Record raw ideas only. Do not summarize, polish, rewrite, or generate a script in this skill.

When the user adds today's idea, always initialize today's workspace first. Use the existing idempotent bootstrapper; do not ask the user to create date folders manually.

## Workflow

1. Resolve the date from the user or today's date.
2. Always run the day bootstrapper before writing the idea:

```bash
npm run new-day -- YYYY-MM-DD
```

3. Write the user's raw wording into `01_inbox/YYYY-MM-DD.md` under the next topic slot.
4. Preserve the problem-purification fields if the template has them:
   - `内容类型：问题解法 / 想法分享`
   - `这条在回答什么问题`
   - `谁会遇到这个问题 / 谁会对这个想法感兴趣`
   - `我这条想给出的最小结论`
5. Fill these fields only when the answer is obvious from the user's raw wording. Otherwise leave them blank for the script stage.
6. Keep `录制状态：未生成脚本`.
7. If `02_scripts/YYYY-MM-DD.md` or `06_logs/YYYY-MM-DD.md` has a stale Day label, fix only the Day label.
8. Stop. Wait for the user to say `生成脚本` or equivalent.

## Rules

- `01_inbox/` is the raw evidence layer. Keep stutters, imperfect phrasing, and oral wording.
- Problem-purification fields are metadata, not a rewrite of the raw wording.
- Do not move the content into `02_scripts/` during intake.
- Auto-creating the day workspace is allowed and required; do not auto-trigger script generation or editing from directory changes.
- Day number increments by successful outputs, not by calendar dates. Prefer `npm run new-day` over manual calculation.
- If the user says there will be more topics today, record the current topic and stop.

## Output

Reply with the date, Day label if known, topic slot updated, and current stage: `原始想法录入`.
