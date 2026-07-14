---
name: video-diary-cleanup
description: Audit Video Workshop cleanup candidates or inspect workflow redundancy. Use when the user asks for morning cleanup, reduce disk usage, or workflow audit. For month-end archive/monthly review/video file scan, use video-diary-monthly-review. Never bulk-delete automatically.
---

# Video Diary Cleanup

## Core Rule

Never bulk delete. Generate reports and ask the user to delete manually or approve one explicit file at a time.

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
- Do not bulk delete files or folders.
- If deletion is needed, stop and ask for manual deletion or explicit one-file approval.
