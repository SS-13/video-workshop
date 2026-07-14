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
  00_state/         ledgers, runs, observations, TopK state
  01_inbox/         raw ideas
  02_scripts/       teleprompter scripts
  03_recordings/    original media
  04_videos/        review and render workspace
  05_exports/       publish package
  06_logs/          production logs
  10_skills/        personal speaking style
  11_templates/关键词收集/  private vocabulary
  15_cover_gallery/ generated cover history
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
```

## Artifacts

| Stage | Canonical artifact | Owner |
| --- | --- | --- |
| Intake | `01_inbox/YYYY-MM-DD.md` | Text Agent |
| Script | `02_scripts/YYYY-MM-DD.md` | Text Agent |
| Source | `03_recordings/YYYY-MM-DD/*` | User, read-only to Agents |
| Review | `04_videos/YYYY-MM-DD/REVIEW.md` | Video Agent |
| Corrected subtitle | `04_videos/YYYY-MM-DD/subtitles/*_corrected.srt` | Video Agent |
| Covers | `05_exports/YYYY-MM-DD/*_cover_3x4.*`, `*_cover_4x3.*` | Video Agent |
| Final video | `05_exports/YYYY-MM-DD/*_video-diary.mp4` | Video Agent |
| Publish copy | `PUBLISH.md`, `publish-package.json` | Video Agent + Compliance Agent |
| Metrics | `00_state/production-stats.csv` | Video Agent |

## Agent Ownership

```text
Orchestrator
  -> Compliance Agent: input/output platform checks
  -> Text Agent: raw idea and script
  -> Video Agent: cover, subtitles, edit, export, publish package, metrics

System Steward Agent
  -> Observation, deduplication, TopK, daily evolution report

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
  -> candidate eligibility
  -> rank
  -> first daily TopK (default 3, frozen)
  -> candidate report
  -> reviewed implementation
  -> tests / Shadow / Canary
  -> explicit activation or rollback
```

The Loop runs only while production is idle. It never replaces the stable route
mid-render.

Production blockers enter this same Observation stream. The daily report renders
a local `生产问题清单`; uncertain issues wait for evidence, while confirmed issues
wait for the next available TopK slot.

## Content Types

- `video-diary`: default, date-first paths, increments Day.
- `suisuinian`: explicit opt-in, column-first paths, no Day increment.
- `reading-note`: explicit opt-in, column-first paths, no Day increment.

Use `python3 09_tools/vp.py route resolve` to inspect a route without executing
it.
