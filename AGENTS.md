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
3. Record idea provenance in the Inbox metadata. Use `灵感来源：生活输入` for
   direct observations or user-supplied thoughts. Use `灵感来源：Sparkling`
   plus an explicit `Sparkling ID：SXXX` only when the user selected that Spark;
   never infer adoption from topic similarity.
4. Run the input compliance review.
5. Build the teleprompter script in `02_scripts/` using the public speaking
   style plus the optional local personal override.
6. Stop after script generation unless the user explicitly asks to edit video.

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
- Never run recursive deletion or ad hoc bulk deletion.
- The only approved multi-file deletion route is the explicitly enabled local
  retention runner. It must resolve, validate, unlink, and log one exact media
  file path at a time; it never deletes directories.
- `edit:render-day-v2` is the default route.
- `edit:render-day-legacy` remains the immediate fallback and must stay usable.

## Local Media Retention

- Public and newly initialized workspaces default to retention disabled.
- Enable it only after the user explicitly chooses a local retention window.
- `retentionDays=3` keeps today and the previous two dates; media dated on or
  before `today - 3 days` becomes eligible.
- Use only `vp cleanup run --apply --if-enabled`. Never replace it with `rm`,
  a recursive directory delete, shell glob deletion, or an improvised script.
- A media file is eligible only when its date-first content item has a
  `publishReady=true` package, `statsRecorded=true`, and a matching row in
  `00_state/production-stats.csv`.
- Skip the entire run while any `production-*.lock.json` exists. Recheck the
  lock, exact path, symlink status, and file size before each unlink.
- Delete only video extensions under `03_recordings/`, `04_videos/`, and
  `05_exports/`. Preserve Inbox, scripts, SRT/ASS, covers, `PUBLISH.md`, JSON,
  statistics, Run State, and cleanup ledgers.
- Every applied run writes a manifest under `06_logs/media-retention/` and one
  append-only ledger row per deleted file in
  `00_state/media-retention-ledger.csv`.

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

An Observation is not automatically a GitHub Issue. Record the affected step,
reproduction/run context, user or artifact loss, priority reason, proposed fix,
validation plan, and possible process gate when known.
Use `vp evolve triage CAND-ID` when that context is learned later; triage-only
events must not increase occurrence counts.

When production is idle, run:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

When GitHub Issues integration is enabled, `observe`, `evolve`, and verified
completion immediately reconcile the rolling Top-K Issues and their public-safe
Issue projection. Manual reconciliation remains available:

```bash
python3 09_tools/vp.py evolve issues sync --date YYYY-MM-DD --if-enabled
```

Rules:

- Unlimited observations may arrive each day.
- Default Top-K Issue limit is 3.
- Top-K Issues are a rolling set of unresolved work slots. New eligible work may
  enter immediately; verified completion releases a slot and refills it from backlog.
- Unfinished issue-ready work carries across dates and is re-ranked in each round.
- Priority alone is not an Issue promotion gate. Promote an anomaly only when it
  is reproducible, repeated, production-blocking, materially costly in rework,
  high-impact, or deterministically confirmed. Explicitly approved features and
  governance changes may also enter.
- `selection.mode=frozen` and explicit `--reselect` remain legacy fallback only.
- Complete a Top-K Issue only with test, artifact, run, or explicit user evidence.
- Completion must record `processAction`: `none`, `test`, `rule`, `gate`,
  `runbook`, or `multiple`.
- Completion is append-only, keeps `releaseTarget=null`, and must not reactivate
  the candidate in a later Loop.
- The Loop produces candidates and reports. It does not silently edit formal
  Skills, Agents, Rules, Hooks, production scripts, or release versions.
- Do not run the Loop while a production lock is active.
- GitHub Issues are a public collaboration projection, not a second source of
  truth. Every active Top-K item gets one Issue, but non-public scopes use a
  redacted title and body. Never upload evidence paths, content IDs, personal passages,
  media, or raw production details.
- Every public-safe Issue contains affected step, reproduction, loss, priority
  reason, proposed fix, validation plan, and process/gate feedback fields.
- Issue type uses `bug`, `feature`, or `other`. Effective priority uses one
  replaceable `priority:P0` through `priority:P3` label and is recalculated on
  every sync. Active, displaced, and completed items use `status:topk`,
  `status:backlog`, and `status:verified` respectively.
- Local completion changes the Issue to `status:verified` but does not close it.
  A PR may use `Closes #N` only after verification; GitHub closes the Issue only
  after that PR merges into the default branch.

### Top-K execution loop

GitHub Issues are an execution queue, not a display-only report. For each active
candidate, use:

```bash
python3 09_tools/vp.py evolve issues start CAND-ID --date YYYY-MM-DD --repo OWNER/REPO --json
git switch -c fix/topk-cand-id
python3 09_tools/vp.py evolve complete CAND-ID --date YYYY-MM-DD \
  --change-type bugfix --evidence path/to/report.md --process-action test
python3 09_tools/vp.py evolve issues check-pr --repo OWNER/REPO --pr N --require-topk
python3 09_tools/vp.py evolve issues merge --repo OWNER/REPO --pr N --apply --auto
```

`start` only creates a bounded work packet; the Agent implements and tests the
fix. Top-K repair PRs use `fix/topk-<candidate-id>`, retain the generated
`Closes #N`, target the default branch, and must be Ready for review. Never close
an Issue manually or equate `status:verified` with a merge. The trusted
`topk-merge` workflow may queue auto-merge only after the Issue gate and required
checks pass. Do not run this loop while a production lock is active, and do not
modify the Stable production path as part of an Issue repair without the normal
Canary and release gates.

### Production blockers

- Record every meaningful production blocker as an Observation with stage,
  impact, evidence, workaround, and content ID.
- Do not patch Stable production code during the active video run.
- Finish through cache, conservative workaround, or legacy fallback when safe.
- After export, triage the issue. Promote only reproducible system defects into
  the next Engineering Loop.
- The generated `生产问题清单` is local. Every Top-K item may have a sanitized or
  redacted Issue projection; never publish raw production details.

## Release Safety

- Keep daily production available while changing the system.
- Validate Candidate changes with tests, Shadow, and Canary where applicable.
- Activate or roll back a release only after explicit user confirmation.
- Never modify production media as part of a release transition.

## Knowledge System Status Contract

- Read `SYSTEM_STATUS.md` and `../99_知识库治理/系统状态通信协议.md` before changing system-level state.
- Use `$publish-system-status` to update this directory's `SYSTEM_STATUS.md` when the active release, production health, blockers, latest verified output, current focus, or core metrics materially change.
- After a successful scheduled evidence check, refresh `checked_at`; preserve `updated_at` when no material state changed.
- Every status claim must point back to local manifests, ledgers, tests, or publish artifacts.
- Do not treat generated files, caches, or unverified media as user output.
- Do not update any other system's status, and do not refresh the timestamp when nothing materially changed.
