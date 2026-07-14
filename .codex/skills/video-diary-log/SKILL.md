---
name: video-diary-log
description: Record Video Workshop run logs, token/time estimates, publish metadata, and sustainability notes. Use when the user asks to 记录日志, 计算 token, 估算耗时, 发布记录, 抖音发布后补充, or summarize today's workflow cost.
---

# Video Diary Log

## Core Rule

Write durable operational records into `06_logs/YYYY-MM-DD.md` for daily runtime notes.

For long-term structured data, use `00_state/` as the canonical layer:

```text
00_state/day-counter.json
00_state/content-ledger.csv
00_state/production-stats.csv
00_state/publish-ledger.csv
```

`06_logs/*.csv` remains a compatibility mirror while older tools are migrated.

Production statistics are recorded at production time, not reconstructed at month end.
Do not rely on files under `03_recordings/`, `04_videos/`, or `05_exports/` for monthly statistics, because those media files may be deleted for disk-space management.

All content columns use the same production ledger. Distinguish content with `column`:

| column | 中文标签 | Day behavior |
| --- | --- | --- |
| `video-diary` | 视频日记 | increments Day |
| `suisuinian` | 碎碎念 | does not increment Day |
| `reading-note` | 读书笔记 | does not increment Day |

## What To Record

In `06_logs/YYYY-MM-DD.md`, update:

- 状态
- 最终视频
- 视频时长
- 抖音状态/链接
- 两秒跳出率/开头留存判断
- 时间记录
- Agent 记录
- Token / 成本记录
- 发布记录
- 可持续性判断
- 问题
- 下次改进

For monthly review metrics, always record after an edit is finished:

- `column`: `video-diary`, `suisuinian`, or `reading-note`.
- `视频时长`: exact seconds when available, otherwise a clear estimate.
- `制作视频总用时`: time from "视频上传/开始剪辑" to final MP4/cover completion.
- `总耗时`: user-reported overall workflow time when available; if unavailable, use `制作视频总用时`.
- `estimated_tokens`: estimated token use when exact usage is unavailable.
- `export_file_size_bytes`: record when the final export still exists, but do not depend on it for future month-end scans.

Also write the same values to `00_state/production-stats.csv` immediately after each final export. Mirror to `06_logs/production-stats.csv` for legacy compatibility.

Use:

```bash
python3 .codex/skills/video-diary-log/scripts/record-production-stats.py --date YYYY-MM-DD --column video-diary --day-label "Day NN" --title "TITLE" --video-path 05_exports/YYYY-MM-DD/FILE.mp4 --cover-path 05_exports/YYYY-MM-DD/COVER.jpg --total-minutes MINUTES --estimated-tokens "120k" --update-daily-log
```

For non-diary columns:

```bash
python3 .codex/skills/video-diary-log/scripts/record-production-stats.py --date YYYY-MM-DD --column suisuinian --title "TITLE" --video-path 05_exports/suisuinian/YYYY-MM-DD_001/FILE.mp4 --cover-path 05_exports/suisuinian/YYYY-MM-DD_001/COVER.jpg --total-minutes MINUTES --estimated-tokens "80k" --allow-missing-time
python3 .codex/skills/video-diary-log/scripts/record-production-stats.py --date YYYY-MM-DD --column reading-note --title "BOOK_OR_TOPIC" --video-path 05_exports/reading-note/YYYY-MM-DD_001/FILE.mp4 --cover-path 05_exports/reading-note/YYYY-MM-DD_001/COVER.jpg --total-minutes MINUTES --estimated-tokens "80k" --allow-missing-time
```

For publish retro, record when available:

- `两秒跳出率`: exact platform value if visible.
- `开头留存判断`: if exact value is unavailable, note the likely opening issue using average watch time, cover click rate, first frame, and first sentence.

## Token Estimates

If exact token usage is unavailable, clearly label it as `估算`. The user prefers estimation over pretending precision.

Keep separate:

- 用户报告 token
- Codex 可见 token
- 估算 token
- 备注

## Publish Ledger

When a video is published or poll data is available, prefer existing tools:

```bash
npm run douyin:poll
npm run douyin:report
```

Do not invent Douyin metrics.

Before month-end review, ensure:

- `00_state/production-stats.csv` has every completed video's `video_duration_seconds`, `production_total_minutes`, and `export_file_size_bytes` when available.
- `00_state/content-ledger.csv` has one row per content item.
- `00_state/publish-ledger.csv` has publish status, publish time, platform URL, and token estimate when known.
- If media files were deleted, do not backfill stats from file scans. Treat `00_state/production-stats.csv` as the source of truth.

## Output

Reply with what log file was updated and the key values recorded.
