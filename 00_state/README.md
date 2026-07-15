# Video Diary State

`00_state` is the durable data layer for this project.

It decouples long-term workflow state from daily folders and large media files:

- `day-counter.json`: the source of truth for video-diary Day numbering.
- `content-ledger.csv`: one row per content item across columns.
- `production-stats.csv`: production cost metrics recorded after final export.
- `publish-ledger.csv`: publish metadata copied from the legacy log ledger.
- `observations/`: append-only updates from Codex, CLI, users, validators, and audits.
- `evolution/`: deterministic daily TopK selection, candidate backlog, and local completion ledger.
- `runs/`: generic 3.0 production run state, one `run.json` per content item.
- `locks/`: runtime leases for observation, production, and evolution writers.

## Daily Engineering Loop

All valid daily updates are retained in `observations/YYYY-MM-DD.ndjson`.

The default daily TopK is `3`, configured in `00_system/evolution-policy.json`. Only the selected TopK enters the day's candidate update list. Remaining updates stay in backlog or `needs-evidence`; they are not deleted.

After a TopK item has verification evidence, `vp evolve complete` appends it to
`evolution/completed/YYYY-MM-DD.json`. Completed items stay visible in the
locked TopK and cannot return to Candidate or backlog. The ledger remains local;
its reusable JSON Schema and example live under `00_system/contracts/`.

P0 is analysis-only and does not modify formal Skills, Rules, Hooks, Agents, production scripts, or versions.

Daily markdown files and video folders can be compacted at month end without
breaking Day increments or monthly statistics.

## Production Stats Rule

Monthly and annual production statistics must come from `00_state/production-stats.csv`.

Do not derive production statistics from whether files still exist in
`03_recordings/`, `04_videos/`, or `05_exports/`. Those folders are media
workspaces and may be cleaned because of local disk limits.

Every edited/exported video must be recorded on the same day it is produced:

- `column`: one of `video-diary`, `suisuinian`, or `reading-note`
- `video_duration_seconds`
- `production_total_minutes`
- `export_file_size_bytes` when the final export still exists
- `estimated_tokens` when available

Current column labels:

| Column | Meaning | Day counter |
| --- | --- | --- |
| `video-diary` | 视频日记 | increments Day |
| `suisuinian` | 碎碎念 | does not increment Day |
| `reading-note` | 读书笔记 | does not increment Day |

Current compatibility rule:

- `00_state/*` is canonical for new data.
- `06_logs/*` remains a legacy/runtime layer until all tools are migrated.
