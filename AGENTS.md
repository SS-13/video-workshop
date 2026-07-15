# Video Workshop Agent Instructions

This repository is a local-first video production system. The tracked files are
the reusable framework. Personal ideas, scripts, recordings, exports, style
profiles, dictionaries, logs, and runtime state stay local and are ignored by
Git.

## First Run

1. Follow `README.md` -> `AI Agent Bootstrap Contract`: detect, install, and
   verify every required dependency.
2. Stop at the user configuration checkpoint and confirm content type,
   platform/cover preset, Day baseline, and personalization choice.
3. Run `npm run setup`.
4. Run `npm run doctor` and require content/render readiness.
5. Run `npm run context` and read the reported `publicReadOrder` in order.
6. If `personalization_status=pending` and the user has approved historical
   content, follow the reported personalization protocol. Read every reported
   source file, keep it unchanged, and write only the local override files.

Do not require personalization before the first video. The public default style
is the fallback.

## Default Route

- Default content type: `video-diary`.
- Use `suisuinian` or `reading-note` only when the user explicitly requests it.
- Resolve commands and ownership from `00_system/`, not from the repository
  folder name.
- Read `.codex/skills/video-diary-orchestrator/SKILL.md` before routing a full
  production request.
- All content uses one date-first key: `YYYY-MM-DD/<content-type>/<sequence>`.
  The default key is `YYYY-MM-DD/video-diary/001`; use `002`, `003`, and so on
  for additional items of the same type on the same date.

## Production Contract

### Idea and script

1. Initialize the date with `npm run new-day -- YYYY-MM-DD`.
2. Preserve the user's raw words in `01_inbox/`; never rewrite them in place.
3. Run the input compliance review.
4. Build the teleprompter script in `02_scripts/` using the public speaking
   style plus the optional local personal override.
5. Stop after script generation unless the user explicitly asks to edit video.

### Recording and review

1. Treat the recording as subtitle truth. The script is context only.
2. Inspect the recording once.
3. Run two independent lanes where possible:
   - cover pair and cover QC;
   - preprocessing, real-audio transcription, correction, and subtitle QC.
4. Produce one combined review pack with the 3:4 cover, 4:3 cover, corrected
   external SRT, low-confidence segments, and insert plan.
5. Do not burn subtitles or apply unconfirmed inserts before the review gate.

### Export and publish package

1. Run the pre-render compliance review on the confirmed SRT and insert plan.
2. Render once with confirmed subtitles, optional one-second cover card, and
   confirmed image inserts.
3. Run technical QC.
4. Generate `PUBLISH.md` and `publish-package.json` from the corrected spoken
   transcript, including title, description, and 3-5 chapters.
5. Record duration, file size, production time, and available token estimate.
6. Report exact paths and publish readiness to the user.

## Quality Invariants

- Subtitle wording and timing come from real spoken audio.
- Maximum two visual subtitle lines.
- Keep subtitles inside the safe area and clear of platform overlays.
- Subtitle accuracy and audio alignment take priority over animation.
- Default video diary has no BGM.
- Never overwrite or move original recordings.
- Never bulk-delete files or directories.
- `edit:render-day-v2` is the default route.
- `edit:render-day-legacy` remains the immediate fallback and must stay usable.

## Personal Data Boundary

Never commit content from ignored local paths. In particular, do not add:

```text
00_state/
01_inbox/
02_scripts/
03_recordings/
04_videos/
05_exports/
06_logs/
10_skills/personal-speaking-style/
11_templates/关键词收集/
15_cover_gallery/
17_reports/
.runtime/
```

Before any public push, scan staged files for credentials, cookies, absolute
home paths, personal passages, and large media.

## Daily Engineering Loop

Workflow corrections are append-only Observations:

```bash
python3 09_tools/vp.py observe --summary "..." --category subtitle-rule --priority P2
```

When production is idle, run:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

After the nightly Loop, project the sanitized locked TopK to GitHub Issues when
the local integration is enabled:

```bash
python3 09_tools/vp.py evolve issues sync --date YYYY-MM-DD --if-enabled
```

Rules:

- Unlimited observations may arrive each day.
- Default TopK is 3.
- The first TopK selection for a date stays locked.
- Later items remain in backlog unless a confirmed P0 production failure
  requires an explicit `--reselect`.
- Complete a TopK item only with test, artifact, run, or explicit user evidence.
- Completion is append-only, keeps `releaseTarget=null`, and must not reactivate
  the candidate in a later Loop.
- The Loop produces candidates and reports. It does not silently edit formal
  Skills, Agents, Rules, Hooks, production scripts, or release versions.
- Do not run the Loop while a production lock is active.
- GitHub Issues are a public collaboration projection, not a second source of
  truth. Every locked TopK gets one Issue, but non-public scopes use a redacted
  title and body. Never upload evidence paths, content IDs, personal passages,
  media, or raw production details.
- Issue type uses `bug`, `feature`, or `other`. Effective priority uses one
  replaceable `priority:P0` through `priority:P3` label and is recalculated
  nightly even after the candidate leaves the next day's TopK.
- Local completion changes the Issue to `status:verified` but does not close it.
  A PR may use `Closes #N` only after verification; GitHub closes the Issue only
  after that PR merges into the default branch.

### Production blockers

- Record every meaningful production blocker as an Observation with stage,
  impact, evidence, workaround, and content ID.
- Do not patch Stable production code during the active video run.
- Finish through cache, conservative workaround, or legacy fallback when safe.
- After export, triage the issue. Promote only reproducible system defects into
  the next Engineering Loop.
- The generated `生产问题清单` is local. Every TopK may have a sanitized or
  redacted Issue projection; never publish raw production details.

## Release Safety

- Keep daily production available while changing the system.
- Validate Candidate changes with tests, Shadow, and Canary where applicable.
- Activate or roll back a release only after explicit user confirmation.
- Never modify production media as part of a release transition.
