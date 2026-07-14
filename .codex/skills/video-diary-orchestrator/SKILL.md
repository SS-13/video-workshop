---
name: video-diary-orchestrator
description: Route Video Workshop requests to the correct project skill. Use for general workflow questions, end-to-end planning, or when the user asks what step comes next. It maps inbox, script, edit, cover, log, remote, cleanup, monthly review, and Douyin tasks.
---

# Video Diary Orchestrator

## Purpose

Use this skill as the routing layer. Do not perform every step from this file. Pick the narrow skill for the requested stage.

## Sub Agent Split

For non-trivial work, keep the main Codex thread light and delegate details to the Sub Agent definitions in `.codex/agents/`:

```text
Compliance Agent -> .codex/agents/compliance-agent.md
Text Agent       -> .codex/agents/text-agent.md
Video Agent      -> .codex/agents/video-agent.md
System Steward   -> .codex/agents/system-steward-agent.md
Release Agent    -> .codex/agents/release-agent.md
```

Use `Compliance Agent` before script generation and after final export.

Use `Text Agent` for raw text and scripts.

Use `Video Agent` for everything after video upload: cover, editing, subtitles, export, and logging. The Video Agent owns the production timer from "start editing" to "final MP4 plus stats recorded".

Use `System Steward Agent` only after production is idle, or on the next day's first run, to collect observations and generate the daily TopK evolution report. Default `K=3`.

Use `Release Agent` for Shadow, real Canary adoption, release readiness, activation, and rollback. It must not modify production media and cannot activate a Candidate without explicit user approval.

## Routing

If the user does not explicitly name `碎碎念` or `读书笔记`, route the work as `video-diary`.

- Raw idea, start today's record, add topic: delegate to Compliance Agent for input review, then Text Agent uses `video-diary-intake`. Today's workspace must be auto-created with `npm run new-day -- YYYY-MM-DD` before writing the idea.
- Generate or revise teleprompter script: after input review, delegate to Text Agent, which uses `video-diary-script`.
- Video uploaded, edit, subtitle, trim black ending, export MP4: delegate to Video Agent, which uses `video-diary-cover`, `video-diary-edit`, and `video-diary-log`.
- Final MP4 exists: delegate to Compliance Agent for output review before publish.
- Cover sample, cover revision, archive cover: delegate to Video Agent, which uses `video-diary-cover`.
- Time/token/production log: delegate to Video Agent, which uses `video-diary-log`.
- Feishu mobile remote entry/worker: use `video-diary-remote`.
- Morning cleanup/workflow audit: use `video-diary-cleanup`.
- Month-end archive, monthly review, production stats, video file scan, or one-file video deletion: use `video-diary-monthly-review`.
- Douyin poll/report/curve: use `video-diary-douyin`.
- Workflow correction, permanent rule request, daily TopK, or evolution report: use `video-production-evolution` through System Steward Agent.
- Candidate/Shadow/Canary, release readiness, activation, or rollback: use `video-production-release` through Release Agent.

## Pipeline

```text
01_inbox -> compliance input review -> 02_scripts -> 03_recordings -> cover draft/final -> 04_videos -> 05_exports -> publish package -> compliance output review -> 06_logs -> 15_cover_gallery
```

After a recording is uploaded, the default production order is two parallel lanes, one combined review gate, then one render:

1. Inspect the recording once.
2. Lane A: use `video-diary-cover` to render the locked 3:4/4:3 cover pair and run cover QC.
3. Lane B: use v2 `video-diary-edit` to tail-scan, cache audio, produce word timestamps, dictionary-correct the SRT, and run text/audio alignment gates.
4. Build `04_videos/YYYY-MM-DD/REVIEW.md` containing both covers, external SRT, review video, low-confidence segments, and insert plan. Ask for one combined confirmation.
5. Run Compliance Agent on the confirmed SRT and insert plan before video rendering. If it returns `revise` or `block`, modify the SRT/plan only.
6. After confirmation and compliance pass, render subtitles, cover card, and confirmed image inserts in one FFmpeg pass.
7. Generate the Douyin publish title, description, and 3-5 smart chapters from the confirmed corrected SRT. Include this copy in the pre-publish compliance review.
8. Package the confirmed covers, final MP4, `PUBLISH.md`, and `publish-package.json` together in the matching export folder, then run technical QC and production logging.
9. Notify the user with the publish title, description, smart chapters, exact export paths, duration, file size, production time, QC status, stats status, and publish-ready status.

Minimal inspection, terminal-tail preprocessing, transcription, SRT correction, and SRT checks may happen before cover confirmation. Do not burn subtitles, apply unconfirmed inserts, or render the final MP4 before both the cover and the external SRT are confirmed.

## Column Path Rule

- Default column is `video-diary`. Other columns are opt-in only.
- `视频日记` keeps date-first folders: `03_recordings/YYYY-MM-DD/`, `04_videos/YYYY-MM-DD/`, `05_exports/YYYY-MM-DD/`.
- `碎碎念` uses column-first folders: `03_recordings/suisuinian/YYYY-MM-DD_001/`, `04_videos/suisuinian/YYYY-MM-DD_001/`, `05_exports/suisuinian/YYYY-MM-DD_001/`.
- `读书笔记` uses column-first folders: `03_recordings/reading-note/YYYY-MM-DD_001/`, `04_videos/reading-note/YYYY-MM-DD_001/`, `05_exports/reading-note/YYYY-MM-DD_001/`.
- Use `_001`, `_002` for multiple uploads in the same column on the same date.
- Only `视频日记` increments Day numbers.

## Invariants

- Required user confirmation is normally one combined review pack covering the cover pair, corrected external SRT, and insert plan. BGM and compliance risk acceptance remain explicit when present.
- `01_inbox` is raw and untouched.
- `视频日记` defaults to one main topic per day.
- `碎碎念` has no strict topic limit and may follow the user's spoken flow.
- Default edit has no BGM.
- Default `video-diary` v2 does not cut spoken video unless filler removal is explicitly requested. `polished` and `碎碎念` currently use the preserved legacy route. This removes the previous standard/polished rule conflict.
- Subtitle quality has priority over speed when the user says so.
- Final upload files live in `05_exports/YYYY-MM-DD/` for `视频日记`, or `05_exports/<column>/YYYY-MM-DD_###/` for other columns.
- Cover revisions live in `15_cover_gallery/YYYY-MM-DD/`.
- Cover pair and corrected external SRT are produced in parallel and delivered as one review pack; final burn-in/export begins after that pack and pre-render compliance are confirmed.
- `edit:render-day-v2` is the default route. `edit:render-day-legacy` remains available as an immediate fallback and must not be deleted during the v2 rollout.
- Compliance input review happens before Text Agent writes the publish script.
- Compliance output review happens before the user publishes.
- Final video generation is not complete until the publish package exists and the user has been shown its title, description, smart chapters, and production result in the main thread.
- Every workflow update may be recorded as an Observation. Only the configured daily TopK enters the candidate update list; all other updates remain in backlog or need more evidence.
- Do not bulk delete.

## Useful Existing Docs

Read only when needed:

```text
START_HERE.md
PIPELINE.md
WORKFLOW.md
.codex/agents/README.md
.codex/agents/compliance-agent.md
.codex/agents/text-agent.md
.codex/agents/video-agent.md
```
