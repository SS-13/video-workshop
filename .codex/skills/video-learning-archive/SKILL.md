---
name: video-learning-archive
description: Archive external videos for learning in Video Workshop. Use when the user provides a video URL/link and asks to 下载, 收藏, 学习, 拆解, 归档, 提取逐字稿, 总结视频, or says a video is worth studying. This skill is separate from video-diary editing and should not process the user's own daily recordings.
---

# Video Learning Archive

## Scope

Use this skill only for external videos the user wants to study. Do not use it for `03_recordings`, `04_videos`, or `05_exports`.

Default storage:

```text
18_learning/
```

Each archived link gets one folder:

```text
18_learning/YYYY-MM-DD_slug/
├── source.json
├── video file downloaded by yt-dlp
├── subtitles/
│   └── transcript.md
├── summary.md
└── notes.md
```

## Workflow

1. Read `references/yt-dlp-policy.md` when platform/login/copyright behavior matters.
2. Run the archive script:

```bash
python3 .codex/skills/video-learning-archive/scripts/archive-video-link.py "URL"
```

Use `--title` when the user gives a learning title:

```bash
python3 .codex/skills/video-learning-archive/scripts/archive-video-link.py "URL" --title "学习标题"
```

3. If `yt-dlp` is missing, report the script's install message and stop. Do not install dependencies unless the user approves it.
4. After the script finishes, open `subtitles/transcript.md` if it exists and write a concise `summary.md`:
   - 核心观点
   - 可学习的方法
   - 可迁移到我的视频/内容工作流的点
   - 值得复看的时间点
5. Update `notes.md` only with user-specific observations or a reusable拆解模板. Keep it brief.

## Rules

- Default to `--no-playlist`; download a playlist only when the user explicitly asks.
- Prefer available official/manual subtitles. Use auto subtitles when manual subtitles are unavailable.
- Do not invent transcript content if subtitles are missing. Mark transcript as unavailable and ask whether to run speech transcription.
- Do not redistribute downloaded media. Treat the archive as personal learning material.
- Keep this workflow independent from the video diary production pipeline.
