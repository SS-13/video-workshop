---
name: video-diary-cover
description: Create, revise, route, and archive covers for Video Workshop. Use when the user asks for 封面, 样稿, 换封面, 字体更大, 黑边更细, cover gallery, or asks to make covers for 视频日记, 碎碎念, or 读书笔记/读书日记. Supports separate evolving cover routes and versions.
---

# Video Diary Cover

## Core Rule

Route the cover by column, render with bundled scripts, and archive every approved or meaningful revision.

Do not hard-code one day's title, Day number, or style into the Skill. Route/style decisions live in `references/`; execution lives in `scripts/`; cover history lives in `gallery/` and `15_cover_gallery/`.

For `视频日记`, keep the current cover form: top-left `视频日记`, top-right date plus `持续记录 DayNN`, large centered main title, yellow subtitle/description tag. Do not remove the top series/date/day information when revising covers or adding a 1-second in-video title card.

Cover is one of the first production deliverables after a recording is uploaded. Extract or receive candidate frames from the raw recording or a minimally preprocessed copy, render cover samples, and confirm the final cover before final MP4 rendering.

SRT generation runs in parallel with cover work. Render the matching 3:4/4:3 pair with one locked route/version, then include both covers and the corrected external SRT in the single `REVIEW.md` confirmation pack. Final subtitle burn-in and final export wait for that combined confirmation.

When the user provides two cover photos, treat them as the default source of truth:

- portrait photo -> 3:4 vertical cover
- landscape photo -> 4:3 horizontal cover

Do not crop a vertical video frame into a horizontal cover unless no landscape photo is available. This avoids oversized heads and preserves the room/background context.

## Required Reads

Read before rendering or revising:

```text
references/cover-routes.md
```

If `15_cover_gallery/INDEX.md` exists, read it as optional local design history.
It is generated from ignored personal cover revisions and is not required in a
clean clone.

Read when changing route configuration:

```text
references/cover-routes.json
```

## Route Selection

- If the column is `视频日记`, use route `video-diary`.
- If the column is `碎碎念`, use route `suisuinian`.
- If the column is `读书笔记` or `读书日记`, use route `reading-note`.
- If the user does not specify a column, default to `video-diary` for existing Day-numbered diary content.

## Render

Use the reusable renderer:

```bash
python3 .codex/skills/video-diary-cover/scripts/render-cover.py --route video-diary --date YYYY-MM-DD --day-label "Day NN" --base-frame path/to/frame.jpg --output 05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover.jpg --title "TITLE" --subtitle "TAGLINE" --note "NOTE"
```

For dual cover delivery, output both:

```text
05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover_3x4.jpg
05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover_4x3.jpg
```

Both variants must keep the same series metadata, main title, subtitle, and current cover style.

Preferred paired command:

```bash
npm run cover:render-pair -- --date YYYY-MM-DD --route video-diary --style-version v1.3.1 --day-label "Day NN" --base-frame-3x4 PORTRAIT --base-frame-4x3 LANDSCAPE --output-prefix 05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover --title "TITLE" --subtitle "SUBTITLE"
```

The pair renderer writes cover QC reports and a pair manifest under `04_videos/YYYY-MM-DD/cover-qc/`, then records the locked route/version and cover paths in `job.json`. Font loading, output dimensions, and title bounds must pass before the cover is presented.

For `碎碎念`, keep the main title fixed and use `--subtitle` for the day's topic:

```bash
python3 .codex/skills/video-diary-cover/scripts/render-cover.py --route suisuinian --date YYYY-MM-DD --base-frame path/to/frame.jpg --output 05_exports/YYYY-MM-DD/YYYY-MM-DD_suisuinian_01_cover.jpg --subtitle "今天随口聊的主题" --note "NOTE"
```

For `读书笔记`, use the book name as the main title and put the expansion in `--subtitle`:

```bash
python3 .codex/skills/video-diary-cover/scripts/render-cover.py --route reading-note --date YYYY-MM-DD --base-frame path/to/frame.jpg --output 05_exports/YYYY-MM-DD/YYYY-MM-DD_reading-note_01_cover.jpg --book-title "书名" --subtitle "章节/观点/阅读感受" --note "NOTE"
```

Patch scripts in `scripts/`, not inline in chat.

## Pencil Export Fallback

When a cover is built in Pencil and MCP `export_nodes` fails or times out, use this fallback path:

1. Export the selected Pencil frame to HTML with `export_html`.
2. Render that HTML to PNG with:

```bash
npm run cover:render-pencil-html -- --input 11_templates/pencil-cover-demos/FRAME.html --output 11_templates/pencil-cover-demos/FRAME.png
```

This is the default recovery path for Pencil-originated covers in this workspace because `export_html` is stable while `export_nodes` may fail on large image-backed frames.

For automated delivery into the normal workflow, point `--output` directly at:

```text
05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover_3x4.png
05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover_4x3.png
```

Or use the wrapped export command:

```bash
npm run cover:export-pencil -- --input 11_templates/pencil-cover-demos/FRAME.html --date YYYY-MM-DD --output-name YYYY-MM-DD_DayNN_cover_3x4.png
```

This wrapper writes directly into `05_exports/YYYY-MM-DD/`.

## Cover + SRT First Flow

When the user says a video has been uploaded and a cover is needed:

1. Locate the matching recording folder.
2. Extract several candidate frames from the raw or minimally preprocessed recording.
3. Show or route the samples for user selection when the user has not already picked a frame.
4. Render the cover for the selected route and title.
5. Put the confirmed cover into the matching `05_exports/.../` folder.
6. Archive meaningful revisions to `15_cover_gallery/.../`.
7. In parallel, `video-diary-edit` may produce a corrected external SRT for user review.
8. Only after both cover and SRT are confirmed should `video-diary-edit` burn subtitles and export the final MP4.

## Archive

Archive every approved or meaningful revision:

```bash
npm run archive-cover -- YYYY-MM-DD --source path/to/cover.jpg --route ROUTE --style-version STYLE_VERSION --title "TITLE" --note "ROUTE VERSION NOTE"
```

Then rebuild the Skill gallery:

```bash
npm run cover:gallery
```

## Rules

- Show samples before overwriting the final cover when the user is still choosing.
- Keep each column visually distinguishable, but preserve one recognizable personal system.
- Do not silently collapse `碎碎念` and `读书笔记` into `视频日记`.
- Add a new style version in `references/cover-routes.json` instead of overwriting an old approved version.
- Fail when configured fonts cannot load. Do not silently use Pillow's default font.
- Use `VIDEO_WORKSHOP_FONT=/absolute/path/to/CJK-font` when the platform does not provide one of the bundled system-font candidates.
- Lock `route + styleVersion` in `job.json`; do not let daily title generation change visual design tokens.
- Keep `15_cover_gallery/YYYY-MM-DD/` as the source image archive.
- Keep `15_cover_gallery/INDEX.md` as the writable design gallery index.
