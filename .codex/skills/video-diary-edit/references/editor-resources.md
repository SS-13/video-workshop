# Editor Resources

## Scripts

Use these bundled scripts for video editing work:

- `scripts/preprocess-recording.py`: trim terminal black screen or watermark from recordings.
- `scripts/transcribe-recording-to-srt.py`: run local Whisper transcription and write SRT.
- `scripts/build-transcription-prompt.py`: build a bounded local Whisper prompt from the current script and keyword dictionary.
- `scripts/build-word-timestamp-srt.py`: build short readable cues directly from Whisper word timestamps.
- `scripts/analyze-transcript-confidence.py`: emit only low-confidence time ranges for targeted review.
- `scripts/correct-transcript.py`: apply transcript correction dictionary.
- `scripts/remove-filler-words.py`: remove isolated filler sounds and shift subtitles.
- `scripts/check-subtitle-srt.py`: check subtitle length and known bad terms.
- `scripts/generate-video-diary-caption-assets.py`: generate SRT/ASS with `--ass-only`; omit `--ass-only` only for polished PNG/concat assets.
- `scripts/render-ass-subtitles.py`: default fast subtitle rendering route.
- `scripts/render-ass-subtitles-legacy.py`: frozen legacy ASS render path.
- `scripts/render-day-v2.py`: optimized word-timestamp/review-gate pipeline.
- `scripts/render-day-legacy.py`: preserved previous deterministic pipeline.
- `scripts/build-review-pack.py`: create the single cover/SRT/insert confirmation pack.
- `scripts/workflow_state.py`: maintain `job.json`, source fingerprints, and stage state.
- `scripts/render-subtitle-overlay.py`: polished PNG/transparent-overlay rendering route.
- `scripts/render-scripted-subtitles.py`: legacy scripted subtitle rendering.
- `scripts/add-picture-in-picture.py`: add picture-in-picture clips.
- `scripts/add-bgm.mjs`: add looped BGM under the original voice track.

## References

- `11_templates/关键词收集/`: project-level keyword library maintained by the user. Check this first for product names, technical terms, book/movie names, and domain vocabulary.
- `11_templates/关键词收集/字幕纠错词库.tsv`: first-priority correction dictionary used by `scripts/correct-transcript.py`.
- `11_templates/关键词收集/专有名词清单.md`: human-readable canonical vocabulary list.
- `00_system/defaults/transcript-corrections.tsv`: public fallback dictionary. The local dictionary may override it and remains ignored by Git.

## Current Default Subtitle Style

Default daily rendering uses the ASS fast route. The polished overlay route is
an optional style variant, not a dependency on a historical personal export.

Default style traits:

- subtitle appears as one caption block at a time
- semi-transparent dark rounded box
- centered white Chinese text
- generous bottom safe area
- max two visual lines
- caption switches by spoken phrase, not karaoke word-by-word
- smooth cut-style replacement from one block to the next

If the user says “按现在这条字幕的流转方式”, use this style as the baseline without re-asking.

## Editing Priority

- Content and spoken meaning come first.
- Subtitle text must come from the real recording and stay aligned to audio.
- Use clear, max-two-line subtitles inside the safe area.
- Prefer ASS fast subtitles for daily edits. Use PNG/overlay subtitles only when the user explicitly asks for the more polished caption-box look or the ASS result is visually insufficient.
- If a cover/title card is needed inside the video, use the confirmed cover for 1.0 second at the start and keep the existing main title/subtitle/top metadata form.

## Engine Routing

- Default: `render-day.py --engine v2`.
- Fallback: `render-day.py --engine legacy`.
- `polished` and legacy resume stages route to the preserved engine automatically.
- Never remove the legacy scripts during a v2 rollout or template revision.

## Boundary

Root-level `09_tools/` is for project automation such as new-day setup, Feishu worker, Douyin polling, monthly archival, cleanup, and audits. Video editing execution logic should stay inside this skill. Cover rendering and cover archives belong to `video-diary-cover`.
