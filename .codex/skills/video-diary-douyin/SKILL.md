---
name: video-diary-douyin
description: Poll and report Douyin publish metrics for Video Workshop. Use when the user asks about Douyin data, 发布情况, 播放曲线, douyin:poll, douyin:report, or wants post-publish analysis by Day/title/time/view changes.
---

# Video Diary Douyin

## Core Rule

Use browser-login based polling tools already in the project. Do not invent metrics. Do not scrape or log into accounts unless the user has explicitly logged in or asked to use the browser route.

## Commands

```bash
npm run douyin:login
npm run douyin:poll
npm run douyin:report
```

## Outputs

Primary data files:

```text
00_state/publish-ledger.csv
06_logs/douyin-videos.csv
06_logs/publish-ledger.csv
```

`00_state/publish-ledger.csv` is the canonical structured copy. `06_logs/publish-ledger.csv` remains a legacy/runtime mirror until the Douyin tools are fully migrated.

Report by Day, title, publish time, view delta, interaction metrics, average watch time, and cover click rate when available.

When available, also report two-second bounce rate. If Douyin does not expose it in the current browser view or polling data, do not invent it; use average watch time, cover click rate, first frame, first subtitle, and first sentence as the opening-retention proxy.

Read opening analysis rules when doing a content retro:

```text
.codex/skills/video-diary-script/references/retention/two-second-retention.md
```

## Analysis Boundary

For content analysis, combine Douyin metrics with the matching `02_scripts/YYYY-MM-DD/<content-type>/<sequence>.md` and final title/cover notes. If using cheat-on-content skills, trigger them explicitly for scoring, prediction, retro, or audience analysis.

For high two-second bounce or weak average watch time, classify likely cause:

- opening visual/audio not attractive enough
- lead-in too slow
- topic comprehension cost too high
- cover/title mismatch with first sentence
