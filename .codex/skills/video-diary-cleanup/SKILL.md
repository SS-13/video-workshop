---
name: video-diary-cleanup
description: Audit cleanup candidates, run explicitly enabled local media retention, or inspect workflow redundancy. Use when the user asks for morning cleanup, automatic old-video cleanup, disk reduction, or workflow audit. For month-end archive/monthly review/video file scan, use video-diary-monthly-review.
---

# Video Diary Cleanup

## Core Rule

Manual cleanup stays report-only or one-file-at-a-time. The sole automated
exception is `vp cleanup run --apply`: it must be enabled in ignored local
workspace configuration after explicit user approval, then validates and logs
each exact file path before unlinking it. Never delete directories or use shell
globs, recursive deletion, or `rm -rf`.

## Retention CLI

```bash
python3 09_tools/vp.py cleanup status --date YYYY-MM-DD
python3 09_tools/vp.py cleanup configure --enabled --days 3
python3 09_tools/vp.py cleanup run --date YYYY-MM-DD
python3 09_tools/vp.py cleanup run --date YYYY-MM-DD --apply --if-enabled
```

The run must skip when a production lock exists. It deletes only video files
inside date-first content directories that have a publish-ready package and a
matching production-statistics row. It preserves text, subtitles, covers,
publish metadata, state, and logs.

## Morning Cleanup

Use the dry-run report:

```bash
npm run morning-cleanup -- YYYY-MM-DD
```

This writes:

```text
06_logs/morning-cleanup-YYYY-MM-DD.md
```

## Workflow Audit

Use:

```bash
npm run audit-workflow
```

## Deletion Rules

- Do not use `rm -rf`.
- Do not use recursive deletion.
- Do not delete folders.
- Outside the configured retention runner, stop and ask for manual deletion or
  explicit one-file approval.
