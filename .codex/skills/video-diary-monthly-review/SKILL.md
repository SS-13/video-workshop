---
name: video-diary-monthly-review
description: Run the Video Workshop month-end review, text archive, production statistics, and video file scan. Use only when the user asks for 月度复盘, 月末归档, monthly review, 年度统计 input, 视频文件扫描, or deleting one explicit video file after review. Never bulk-delete automatically.
---

# Video Diary Monthly Review

## Core Rule

Use this skill outside the daily workflow, usually on the last day of the month or when the user explicitly asks for a month-end archive.

Do not bulk delete. The bundled script may scan all videos and create a deletion manifest, but actual deletion is limited to one explicit video file at a time.

## Required Read

Read before running destructive-adjacent work:

```text
references/monthly-review-policy.md
```

## Month-End Review

Run:

```bash
python3 .codex/skills/video-diary-monthly-review/scripts/monthly_review.py review YYYY-MM
```

This writes:

```text
16_monthly_archive/YYYY-MM/
├── INDEX.md
├── YYYY-MM_month-document.md
├── inbox.md
├── scripts.md
├── logs.md
├── publish-ledger-YYYY-MM.csv
└── video-files.md
```

The review combines the month text files and summarizes production statistics from `00_state/production-stats.csv` first. Current video file scans are cleanup manifests only; do not use local file existence under `03_recordings/`, `04_videos/`, or `05_exports/` as the source of truth for monthly production statistics. The tool may fall back to legacy logs for older months, scans current video file size for cleanup, and deletes nothing.

`YYYY-MM_month-document.md` is the month-folder single document for reading and handoff. It contains `INDEX.md` plus the full `scripts.md` content.

## Scan Videos

Run a full project scan:

```bash
python3 .codex/skills/video-diary-monthly-review/scripts/monthly_review.py scan-video
```

Run a month scan:

```bash
python3 .codex/skills/video-diary-monthly-review/scripts/monthly_review.py scan-video --month YYYY-MM
```

## Collect Text Before Video Cleanup

Before the user deletes video media files, preserve all text-side assets from the month:

```bash
python3 .codex/skills/video-diary-monthly-review/scripts/collect-text-archive.py YYYY-MM
```

This writes:

```text
16_monthly_archive/YYYY-MM/
├── text-manuscripts.md
├── text-assets-index.md
└── text-assets/files/
```

It copies only text assets such as raw inbox notes, scripts, SRT subtitle files, transcript correction notes, edit notes, logs, CSV/JSON metadata, and cover indexes. It copies no MP4/MOV/WebM files and deletes nothing.

## Delete One Video

Only after the user names one explicit project-relative video path:

```bash
python3 .codex/skills/video-diary-monthly-review/scripts/monthly_review.py delete-one path/to/file.mp4
```

This is a dry run. If the user confirms that exact file:

```bash
python3 .codex/skills/video-diary-monthly-review/scripts/monthly_review.py delete-one path/to/file.mp4 --yes
```

The script refuses paths outside the project and refuses non-video files.

## Daily Logging Dependency

For monthly stats to work, each daily edit should record:

- `视频时长`
- `制作视频总用时` or `总耗时`
- `estimated_tokens` or daily token estimate in the ledger/log

Prefer writing those values to `00_state/production-stats.csv` through `video-diary-log`. `06_logs/production-stats.csv` remains a compatibility mirror. `publish-ledger.csv` remains the publish/platform ledger, with `00_state/publish-ledger.csv` as the canonical structured copy.
