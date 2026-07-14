# Video Diary Project Skills

These project-local skills define the Video Workshop workflow.

Current Sub Agent definitions live in:

```text
.codex/agents/
```

Use:

- `Text Agent`: raw ideas, `01_inbox`, script generation, script revision.
- `Video Agent`: cover, edit, subtitles, export, logs, and `00_state` production statistics.

Use the narrowest matching skill:

- `video-diary-orchestrator`: route a general request.
- `video-diary-intake`: record raw thoughts into `01_inbox/`.
- `video-diary-script`: generate or revise teleprompter scripts.
- `video-diary-edit`: trim recordings, create accurate subtitles, export MP4.
- `video-diary-cover`: render and archive Douyin-style covers.
- `video-diary-log`: record time, token, cost, publish notes.
- `video-diary-remote`: control Feishu mobile worker.
- `video-diary-cleanup`: audit daily cleanup and workflow redundancy.
- `video-diary-monthly-review`: archive monthly text, summarize stats, scan video files.
- `video-diary-douyin`: poll/report Douyin metrics.

Mechanical work should live in skill `scripts/` first. `09_tools/` is the legacy tool layer. Skills should hold workflow rules and call scripts instead of redoing repeatable work in model context.
