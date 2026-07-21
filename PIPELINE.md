# Video Workshop Pipeline

## Two Layers

The repository separates reusable system files from private production data.

```text
Tracked framework
  00_system/        control plane, profiles, registries, release policy
  .codex/agents/    Agent ownership
  .codex/skills/    executable workflow knowledge
  09_tools/         deterministic CLI and automation
  AGENTS.md         canonical AI entry

Ignored workspace
  00_state/         ledgers, runs, observations, Top-K Issue state
  01_inbox/         raw ideas
  02_scripts/       teleprompter scripts
  03_recordings/    original media
  04_videos/        review and render workspace
  05_exports/       publish package
  06_logs/          production logs
  10_skills/        personal speaking style
  11_templates/关键词收集/  private vocabulary
  15_cover_gallery/ Pencil design versions + generated cover history
  17_reports/       local evolution and release reports
```

## Production Flow

```text
raw idea
  -> input compliance
  -> script
  -> recording
  -> inspect once
     |-> cover pair + cover QC
     |-> preprocess + transcription + correction + subtitle QC
  -> combined review pack
  -> pre-render compliance
  -> one final render
  -> technical QC
  -> publish package + metrics
  -> completion notice
  -> production issue triage
     -> confirmed fixes enter the next Engineering Loop
  -> opt-in media retention
     -> publish/statistics/lock gates
     -> exact-path deletion ledger
```

Cover has its own compact control plane:

```text
Pencil style design -> vp cover design -> immutable style version
daily sources       -> vp cover make   -> pair + QC + archive
version inspection  -> vp cover history
```

## Artifacts

| Stage | Canonical artifact | Owner |
| --- | --- | --- |
| Intake | `01_inbox/YYYY-MM-DD/<content-type>/<sequence>.md` | Text Agent |
| Script | `02_scripts/YYYY-MM-DD/<content-type>/<sequence>.md` | Text Agent |
| Source | `03_recordings/YYYY-MM-DD/<content-type>/<sequence>/*` | User, read-only to Agents |
| Review | `04_videos/YYYY-MM-DD/<content-type>/<sequence>/REVIEW.md` | Video Agent |
| Corrected subtitle | `04_videos/YYYY-MM-DD/<content-type>/<sequence>/subtitles/*_corrected.srt` | Video Agent |
| Covers | `05_exports/YYYY-MM-DD/<content-type>/<sequence>/*_cover_3x4.*`, `*_cover_4x3.*` | Video Agent |
| Final video | `05_exports/YYYY-MM-DD/<content-type>/<sequence>/*.mp4` | Video Agent |
| Publish copy | `PUBLISH.md`, `publish-package.json` | Video Agent + Compliance Agent |
| Metrics | `00_state/production-stats.csv` | Video Agent |
| Retention audit | `00_state/media-retention-ledger.csv`, `06_logs/media-retention/*.json` | System Steward Agent |

## Agent Ownership

```text
Orchestrator
  -> Compliance Agent: input/output platform checks
  -> Text Agent: raw idea and script
  -> Video Agent: cover, subtitles, edit, export, publish package, metrics

System Steward Agent
  -> Observation, triage, Top-K Issues, verification, daily evolution report

Release Agent
  -> Shadow, Canary, activation, rollback
```

Production Agents do not modify formal system rules. System Steward does not
edit production media. Release Agent does not create or re-encode a daily video.

## Daily Evolution Flow

```text
unlimited observations
  -> normalize
  -> deduplicate
  -> Issue-readiness gate
  -> rank
  -> rolling Top-K Issues (default 3)
  -> GitHub public-safe projection
  -> candidate report
  -> reviewed implementation
  -> tests / Shadow / Canary
  -> explicit process feedback: none / test / rule / gate / runbook / multiple
  -> append-only completion ledger
  -> release slot and re-rank unfinished work
  -> Release candidate with no target version
  -> explicit activation or rollback
```

The Loop runs only while production is idle. It never replaces the stable route
mid-render.

Production blockers enter this same Observation stream. The daily report renders
a local `生产问题清单`; uncertain observations wait for evidence, while confirmed
issues wait for the next available Top-K slot. Unfinished issues carry across
dates and remain eligible for re-ranking.

## Content Types

- Every type uses `YYYY-MM-DD/<content-type>/<sequence>` paths.
- `video-diary`: default, increments Day.
- `suisuinian`: explicit opt-in, no Day increment.
- `reading-note`: explicit opt-in, no Day increment.

Use `python3 09_tools/vp.py route resolve` to inspect a route without executing
it.
