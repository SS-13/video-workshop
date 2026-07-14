# yt-dlp Policy

## What yt-dlp is used for here

`yt-dlp` is the deterministic downloader for external learning videos. Official project:
https://github.com/yt-dlp/yt-dlp

Use it to fetch:

- video/audio files
- metadata JSON
- manual subtitles
- auto-generated subtitles when manual subtitles are unavailable

This skill uses `yt-dlp` as a local utility. It does not replace platform review, content judgment, or copyright compliance.

## Default command shape

Use one-video mode by default:

```bash
yt-dlp --no-playlist --write-info-json --write-subs --write-auto-subs --sub-langs "zh.*,en.*" --convert-subs srt --merge-output-format mp4 -o "18_learning/<item>/%(title).200B [%(id)s].%(ext)s" "URL"
```

The project script wraps this command and creates the folder structure automatically.

## Login and cookies

Some platforms require cookies for age-restricted, private, paid, or region-restricted videos. Do not use browser cookies unless the user explicitly approves it for that link.

If a download fails because login is required, report it and ask whether to retry with a cookie option.

## Copyright and platform boundaries

- Archive only links the user provides or explicitly asks to study.
- Use downloads for personal learning, transcript extraction, and content analysis.
- Do not help redistribute downloaded media.
- Prefer downloading subtitles/transcripts when that satisfies the learning task.

## Failure handling

- If subtitles are missing, leave `subtitles/transcript.md` with a clear unavailable note.
- If the video download fails but metadata is available, keep the metadata folder and report the failure.
- If `yt-dlp` is missing, ask the user before installing.
