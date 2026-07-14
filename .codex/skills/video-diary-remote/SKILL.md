---
name: video-diary-remote
description: Operate the Feishu remote intake/script worker for Video Workshop. Use when the user says 出门, go-out, 远程脚本入口, 飞书监听, 关闭监听, worker 状态, or asks how to get scripts from mobile via Feishu.
---

# Video Diary Remote

## Core Rule

The worker is a remote intake/script bridge, not a full auto-edit trigger. It may write raw ideas and scripts, but it must not start video editing by itself.

## Commands

```bash
npm run go-out
npm run come-back
npm run feishu-worker:status
npm run feishu-worker:logs
npm run feishu-worker:dry-run
```

## Rules

- `go-out` starts both `caffeinate` and the Feishu worker so the Mac does not sleep.
- `come-back` stops both.
- Worker status is recorded in `06_logs/feishu-worker-status.json`.
- Worker logs are in `06_logs/feishu-worker.log`.
- If the first idea of a new day arrives remotely, ensure the day workspace exists.
- Raw ideas go to `01_inbox/YYYY-MM-DD.md`; scripts go to `02_scripts/YYYY-MM-DD.md`.

## Output

Report whether the worker is running, PID if shown, last poll/cycle if available, and what the user can do from mobile next.
