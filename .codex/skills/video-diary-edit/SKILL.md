---
name: video-diary-edit
description: Edit and export a video diary MP4 in Video Workshop. Use when the user says 视频上传了, 开始剪辑, 做今天的视频, 输出成片, 加字幕, 去掉结尾黑屏 or similar. Handles recordings, trimming, transcription, subtitle QC, final MP4, and export folder.
---

# Video Diary Edit

## Core Rule

Produce the publish pack in `05_exports/YYYY-MM-DD/<content-type>/<sequence>/`. Default edit is: trim terminal black screen/watermark, add accurate subtitles, no BGM, no brightness/quality enhancement unless explicitly requested.

If the user does not explicitly name `碎碎念` or `读书笔记`, treat the edit as `video-diary`.

First principle: content is the product. Editing must prioritize accurate spoken content, subtitle correctness, timeline sync, readability, and safe areas over motion effects. Do not use dynamic subtitles, HyperFrames, picture effects, or other visual treatments when they make timing, accuracy, or review harder. Daily edits default to the ASS fast subtitle route; use PNG/transparent overlay only as an explicit polished branch.

Subtitle timing is owned by the real audio transcript, not by visual taste. Do not retime subtitle blocks to make captions read prettier. Correct words first, keep the source timing, and only split text inside the original cue window.

The standard production order after upload is cover and SRT first, one combined review gate, then one final render. Make the cover and corrected external SRT in parallel. Build `04_videos/YYYY-MM-DD/<content-type>/<sequence>/REVIEW.md` and hand the cover pair, review video, external SRT, uncertain transcript segments, and insert plan to the user together. Do not burn subtitles until the combined review is confirmed.

The review-pack command also creates `04_videos/YYYY-MM-DD/<content-type>/<sequence>/review/` with two relative links: `video.mp4` and `subtitles.srt`. Use that folder when a browser subtitle tool requires both inputs. The links point to the canonical working video and corrected SRT; do not copy or edit them in place.

If the matching final cover has not been confirmed yet, full final rendering still waits. Minimal recording inspection, terminal-tail preprocessing, transcription, dictionary correction, and SRT timing checks may happen in parallel with cover work because they do not write the final MP4.

The default `video-diary` engine is `v2`: tail scan once, extract/cache audio once, transcribe once with word timestamps and project vocabulary, correct/check SRT, stop at the combined review gate, then render once after confirmation. Each v2 job stores its source fingerprint, style versions, artifacts, and stage state in the matching `04_videos/YYYY-MM-DD/<content-type>/<sequence>/job.json`.

Keep the previous deterministic engine available as `legacy`. Do not delete or silently rewrite it. `polished` mode and non-default column paths automatically fall back to `legacy` until their v2 migration is explicitly completed.

Use `polished` mode only when the user explicitly requests removing meaningless filler sounds from the actual video, or when `column=suisuinian`. In `polished` mode, remove filler sounds from the actual audio/video, not just subtitles. Target clear filler-only sounds: `嗯/呃/啊/额/唔/哎/诶/唉/哎呀/哎哟/哎呦`. Do not cut meaningful words like `然后`, `就是`, or `那个`.

Daily deterministic editing should prefer the Python route before using LLM reasoning. For the first pass after upload, use v2 and stop at the combined review gate:

```bash
npm run edit:deps
npm run edit:render-day-v2 -- --date YYYY-MM-DD --model base --stop-after-review
```

After the user confirms the cover pair and external SRT, resume without retranscription and render once:

```bash
npm run edit:render-day-v2 -- --date YYYY-MM-DD --from-stage review --confirmed --video-input VIDEO --srt-input CONFIRMED_SRT
```

Use the preserved channel when v2 has a regression or when the task needs the existing polished route:

```bash
npm run edit:render-day-legacy -- --date YYYY-MM-DD --mode standard --model tiny --stop-after-srt
```

LLM context is reserved for content judgment, pre-render compliance review, low-confidence subtitle exceptions, title/timeline wording, and user-facing decisions. Do not send the full project or full transcript to a high-tier model for routine editing.

Use bundled scripts from this skill, not root-level `09_tools/`, for video editing operations. Read `references/editor-resources.md` when you need the full script/resource map.

For opening retention decisions, read `.codex/skills/video-diary-script/references/retention/two-second-retention.md`.

For subtitle visual flow, default to ASS fast subtitles for speed. Daily
Douyin-oriented subtitles should sit near the speaker's chin/neck area instead
of the lower publishing UI zone, with a subtle translucent dark background for
readability. If the user asks for a polished caption-box style, preserve these
same safe-area and max-two-line rules.

If the user wants the cover visible inside the video, prepend the confirmed cover as a 1.0 second title card by default. Keep the same main title/subtitle structure as the cover, optionally add a short bottom description, then shift subtitles/audio-video timeline accordingly. Do not add this title card when the user asks for an edit-only export.

## Inputs

Required:

```text
02_scripts/YYYY-MM-DD/<content-type>/<sequence>.md
03_recordings/YYYY-MM-DD/<content-type>/<sequence>/
```

Output:

```text
05_exports/YYYY-MM-DD/video-diary/001/YYYY-MM-DD_DayNN_video-diary.mp4
```

## Column Paths

Default column is `video-diary`. Other columns are opt-in only.

`视频日记` keeps the original date-first path because Day numbering belongs only to the diary series:

```text
03_recordings/YYYY-MM-DD/<content-type>/<sequence>/
04_videos/YYYY-MM-DD/<content-type>/<sequence>/
05_exports/YYYY-MM-DD/<content-type>/<sequence>/
```

For `碎碎念` and `读书笔记`, use the same date-first key and increment only the sequence:

```text
03_recordings/suisuinian/YYYY-MM-DD_001/
04_videos/suisuinian/YYYY-MM-DD_001/
05_exports/YYYY-MM-DD/suisuinian/001/

03_recordings/reading-note/YYYY-MM-DD_001/
04_videos/reading-note/YYYY-MM-DD_001/
05_exports/YYYY-MM-DD/reading-note/001/
```

Use `_001`, `_002` when one column has multiple uploads on the same date. Do not increment the `视频日记` Day number for `碎碎念` or `读书笔记`.

## Modes

### Standard Mode

Default for `video-diary`. The optimized v2 route is:

```text
tail-only scan -> cached 16k audio -> base word timestamps -> vocabulary correction -> confidence report -> text/audio timing gates -> combined review -> compliance -> one ASS render -> log
```

Preferred command:

```bash
python3 .codex/skills/video-diary-edit/scripts/render-day.py --engine v2 --date YYYY-MM-DD --model base --stop-after-review
```

The first command produces `job.json`, word-level JSON, corrected SRT, confidence/QC reports, and `REVIEW.md`, with no burned-in MP4. After confirmation, resume with `--from-stage review --confirmed`. Compliance content review happens on the final SRT and confirmed insert plan before rendering; post-render review is technical only.

Legacy resume commands remain available for existing jobs:

```bash
python3 .codex/skills/video-diary-edit/scripts/render-day.py --engine legacy --date YYYY-MM-DD --from-stage check --video-input VIDEO --srt-input CORRECTED_SRT
python3 .codex/skills/video-diary-edit/scripts/render-day.py --engine legacy --date YYYY-MM-DD --from-stage ass --video-input VIDEO --srt-input CORRECTED_SRT
python3 .codex/skills/video-diary-edit/scripts/render-day.py --engine legacy --date YYYY-MM-DD --from-stage render --video-input VIDEO --ass-input ASS
```

### Polished Mode

Default for `suisuinian`; also use when the user explicitly asks to remove fillers from the actual video.

```text
trim -> rough SRT -> remove fillers from video -> final SRT -> correct/check SRT -> ASS fast render -> one final export -> log
```

Preferred command:

```bash
python3 .codex/skills/video-diary-edit/scripts/render-day.py --date YYYY-MM-DD --mode polished --model tiny
```

## Standard Pipeline

1. Inspect recordings.
2. Check the opening: no black screen, dead air, app watermark, or slow unrelated lead-in before the first useful sentence.
3. If the final cover is not confirmed, extract cover candidates from the raw or minimally preprocessed recording and hand cover work to `video-diary-cover`. Resume this edit pipeline only after the cover exists in the matching export folder.
4. Trim each uploaded recording's terminal black screen/watermark:

```bash
python3 .codex/skills/video-diary-edit/scripts/preprocess-recording.py --date YYYY-MM-DD --all
```

5. Standard mode: transcribe the trimmed input once and record the SRT export checkpoint. Prefer a fast, tool-based path over long token reasoning:

```bash
python3 .codex/skills/video-diary-edit/scripts/transcribe-recording-to-srt.py --date YYYY-MM-DD --input TRIMMED_INPUT --output RAW_SRT --model tiny --language Chinese
```

V2 defaults to `whisper.cpp + ggml-base` for Chinese because it produces token timestamps and confidence locally without the severe CPU word-alignment cost of PyTorch Whisper. If whisper.cpp or its model is unavailable, the same command falls back to OpenAI Whisper. Repeated `tiny -> base` full-video reruns are not part of the v2 default. Use a stronger model only for the reported low-confidence time ranges, not the full video.

6. Polished mode only: create a clean spoken-video version before final subtitle work. First use the rough SRT to locate filler sounds:

```bash
python3 .codex/skills/video-diary-edit/scripts/remove-filler-words.py --date YYYY-MM-DD --input-video TRIMMED_INPUT --input-srt ROUGH_SRT --output-video CLEAN_SPOKEN_VIDEO --output-srt ROUGH_CLEAN_SRT --aggressive-fillers
```

The clean spoken-video file is the source for final subtitles and final rendering. It should remove all clearly meaningless `嗯/呃/啊/额/唔/哎/诶/唉/哎呀/哎哟/哎呦` fillers throughout the video, plus isolated filler-only blocks and leading filler at the start of subtitle blocks. Do not cut meaningful words such as `然后`, `就是`, or `那个`.

Then transcribe the clean spoken-video file:

```bash
python3 .codex/skills/video-diary-edit/scripts/transcribe-recording-to-srt.py --date YYYY-MM-DD --input CLEAN_SPOKEN_VIDEO --output RAW_SRT --model tiny --language Chinese
```

The matching Script file is not the subtitle source of truth. The speaker may add, delete, reorder, or rephrase during recording. Treat the real recording as authoritative for subtitle wording and timing.

7. Correct subtitles and record the subtitle correction checkpoint. Use `scripts/correct-transcript.py` and/or write a corrected SRT. Required corrections include product names, technical terms, book/movie names, obvious homophones, and any places where the speaker diverged from the script. Check the project-maintained keyword library first:

```text
11_templates/关键词收集/字幕纠错词库.tsv
11_templates/关键词收集/专有名词清单.md
```

`correct-transcript.py` reads the optional local
`11_templates/关键词收集/字幕纠错词库.tsv` first, then the public
`00_system/defaults/transcript-corrections.tsv`. If neither contains a rule, it
still emits an unchanged corrected SRT and report.

Timing rule: keep the transcription model's cue start/end times unless audio review proves they are wrong. Do not rebuild timing from the script or from ideal reading rhythm. If a cue must be split for max-two-line readability, split it within the original cue window by proportional word/character position, or use word-level timestamps when available. Prefer shorter cues around 1.2-2.5 seconds and 12-18 Chinese characters, but never improve readability by moving text away from its spoken moment.

8. Run the automatic subtitle gate before user review and before rendering video:

```text
SRT path
字幕条数
字幕 QC 结果
抽查到的错词/长字幕问题
时间戳主题列表
```

Do not generate subtitle PNG assets or render the final MP4 until both automatic checks pass and the user has reviewed/confirmed the external SRT:

- 字幕准确度：known bad terms are absent, project keyword corrections are applied, no obvious broken product/book/movie/tool terms remain, and the SRT follows the real spoken transcript rather than the script.
- 轨道准确度：SRT starts and ends within the usable video duration, cues are monotonic and non-overlapping, and cue boundaries are compared against Whisper word timestamps. The gate reports p95 start/end boundary deltas and sustained global offset; a structurally valid but audio-shifted SRT must fail.

If either check fails, fix the SRT first and rerun the gate. Record pass/fail, elapsed time, and the checked SRT path in the daily log. After the automatic gate passes, hand the SRT path to the user for local browser/player review. If the user sends corrections, edit only the SRT and rerun the gate. Burn subtitles only after the user confirms the SRT.

Recommended first-pass command:

```bash
python3 .codex/skills/video-diary-edit/scripts/render-day.py --date YYYY-MM-DD --mode standard --model tiny --stop-after-srt
```

9. After user SRT confirmation, generate ASS assets from the confirmed SRT. Daily standard mode must use `--ass-only` so it does not generate PNG caption assets:

```bash
python3 .codex/skills/video-diary-edit/scripts/generate-video-diary-caption-assets.py --date YYYY-MM-DD --duration CLEAN_DURATION --srt-input CORRECTED_SRT --ass-only
```

Cover rendering belongs to `video-diary-cover`, not this skill.

Do not generate final subtitle assets from script-derived captions unless the user explicitly asks for scripted captions. Default path is always the corrected SRT generated from `CLEAN_SPOKEN_VIDEO`.

10. Daily standard mode: burn subtitles with the ASS fast route:

```bash
python3 .codex/skills/video-diary-edit/scripts/render-ass-subtitles.py --date YYYY-MM-DD --input VIDEO_INPUT --output DRAFT_MP4 --ass-input ASS_INPUT --duration CLEAN_DURATION
```

Use transparent overlay route only when the user explicitly asks for the polished caption-box style:

```bash
python3 .codex/skills/video-diary-edit/scripts/render-subtitle-overlay.py --date YYYY-MM-DD --input CLEAN_SPOKEN_VIDEO --output DRAFT_MP4 --concat-input OVERLAY_CONCAT --overlay-output OVERLAY_MOV --duration CLEAN_DURATION
```

If adding still images or picture overlays, first show the user an insertion plan and wait for confirmation:

```text
00:12-00:18 | image path | position/size | reason
```

Every static image input must be bounded by the real output duration (`-t DURATION`, `-shortest`, or an equivalent trim). Never run an ffmpeg command with unbounded `-loop 1` image inputs. This can make a 4-minute video encode as a 10+ minute corrupt file. The final output duration must not exceed the main video's duration.

11. Copy only one final MP4 into the matching `05_exports/.../` folder next to the confirmed cover. Keep draft/sync/resync/with-images/hyperframes versions in `04_videos/.../`, not in `05_exports/.../`.
12. Promote the final MP4 and record stats with the fixed script. `--date` is the content date. `--started-at` / `--finished-at` are production timestamps and may fall on a later calendar day:

```bash
python3 .codex/skills/video-diary-edit/scripts/promote-final.py --date YYYY-MM-DD --content-type video-diary --sequence 001 --input 04_videos/YYYY-MM-DD/video-diary/001/FINAL.mp4 --cover 05_exports/YYYY-MM-DD/video-diary/001/COVER.jpg --day-label "Day NN" --title "TITLE" --started-at "YYYY-MM-DD HH:MM" --finished-at "YYYY-MM-DD HH:MM"
```

Record `column`, `视频时长`, `制作视频总用时`, and final export file size immediately through `video-diary-log` / `00_state/production-stats.csv`. These fields are mandatory monthly review inputs and must be captured during production, because old media files may be deleted later.

13. Read `references/publish-package.md`. Generate the Douyin title, publish description, and smart chapters from the confirmed corrected SRT. Run Compliance Agent on this publish copy, then write `PUBLISH.md` and `publish-package.json` next to the final MP4 and cover pair. Fill actual duration, file size, production time, QC status, system version, and stats status after export.

When an Active 3.x Release is present, `publish:package` automatically finalizes this publish-ready package into native Stable Run State. While `2.1.0` is Active, the hook is a verified no-op and must not create or update any Run.

## Stage Timing Checkpoints

Record these checkpoints in `06_logs/YYYY-MM-DD/<content-type>/<sequence>.md` during production:

```text
SRT 导出：start / finish / elapsed / output path
口播清理：start / finish / elapsed / clean spoken-video path / filler report path
字幕修改：start / finish / elapsed / corrected SRT path
字幕准确度检查：start / finish / elapsed / pass-fail / checked SRT path
轨道准确度检查：start / finish / elapsed / pass-fail / checked SRT path
视频生成：start / finish / elapsed / final MP4 path
```

Keep `00_state/production-stats.csv` as the monthly summary source. It only needs the final total production time, video duration, and file size; detailed stage timing stays in the daily log.

## Subtitle Quality Gate

This is mandatory when the user emphasizes subtitle quality:

- Audio/video/subtitle timing must be based on the real recording, not estimated from the script.
- Word correction must not drift timing: fix wrong words separately from cue timing, and only retime after listening or word-level timestamp evidence.
- Max two lines visually.
- Keep left/right safe area around 20%.
- Keep burned-in subtitles above Douyin's bottom interaction/title area by default; current ASS style uses a chin/neck-area placement with translucent backing.
- Text must be large and clear enough for mobile viewing.
- Use real口播 transcription, not scripted subtitles, unless the user asks for scripted captions.
- Compare the transcript against the real spoken content, not only against `02_scripts`. If the speaker improvised, keep the spoken version.
- Remove meaningless filler subtitles before asset generation.
- Review `*_filler_removal_report.json`; isolated filler blocks, leading filler cuts, and aggressive filler cuts may be cut from video before final SRT generation.
- Check known bad terms in SRT with `rg`.
- Extract verification frames and inspect them before finalizing.

## First Two Seconds Gate

Before finalizing:

- First frame should be visually readable and not blocked by UI-safe areas.
- First spoken line should arrive quickly; trim avoidable silence at the start.
- First subtitle should be short, accurate, and not more than two lines.
- If the recording has a stronger hook later and cutting it forward preserves meaning, consider using it as the opening.
- Do not add BGM or effects only for retention unless the user asks; this diary workflow remains voice-first.

## Multi-Clip Rule

If there are multiple recordings, each clip must be preprocessed independently. Do not assume only the last clip has a black tail.

## Stop Condition

After the MP4 exists in the matching export folder next to the confirmed cover, update the matching log and `00_state/production-stats.csv` through `video-diary-log`; keep `06_logs/production-stats.csv` as a legacy mirror. This same rule applies to `video-diary`, `suisuinian`, and `reading-note`. Do not leave production duration or video duration for month-end reconstruction. Generate `PUBLISH.md` and `publish-package.json`, then notify the user in the main thread with this fixed completion format:

```text
标题：
描述：
智能章节：
00:00｜...

视频路径：
封面 3:4：
封面 4:3：
视频时长：
文件大小：
制作耗时：
字幕检查：
合规检查：
00_state 记录：
发布状态：
```

The task is incomplete if the video exists but the publish title, description, smart chapters, or production result has not been shown to the user.

Do not postpone cover work to the end unless the user explicitly requests an edit-only run.
