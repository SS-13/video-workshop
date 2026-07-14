# Monthly Review Policy

## Timing

Use this skill at month end, after the user has finished the month review or asks to inspect/archive media-heavy files.

It is not part of the normal daily pipeline.

## Archive Scope

The month archive keeps text and metadata:

- `01_inbox/YYYY-MM-DD.md`
- `02_scripts/YYYY-MM-DD.md`
- `06_logs/YYYY-MM-DD.md`
- monthly rows from `00_state/publish-ledger.csv`, with `06_logs/publish-ledger.csv` as fallback
- monthly video file manifest
- production stats derived from `00_state/production-stats.csv`, with daily logs and publish ledger as fallback

The archive does not copy MP4/MOV/WebM video files.

## Statistics

Monthly stats should include:

- video count from `00_state/production-stats.csv`
- column distribution from `00_state/production-stats.csv`
- known total video duration from production-time records
- known production/manual time from production-time records
- known final export size from production-time records when available

Do not use current files under `03_recordings/`, `04_videos/`, or `05_exports/`
as the source of truth for production statistics. They may be deleted after
publishing or after month-end cleanup because of disk-space limits.

Video file scans are only for cleanup manifests:

- current local video file count and size
- current local video size by stage: `recordings`, `videos`, `exports`

For annual review, aggregate `00_state/production-stats.csv`, `00_state/publish-ledger.csv`, and the generated `16_monthly_archive/YYYY-MM/INDEX.md` files.

## Safe Deletion Boundary

Never bulk-delete.

Allowed:

- scan all video files
- generate `video-files.md`
- dry-run one explicit file deletion
- delete one explicit project-relative video file after confirmation

Not allowed:

- deleting directories
- recursive deletion
- deleting multiple files in one command
- deleting non-video files
- deleting paths outside the project

If the user asks to delete all monthly videos, generate the manifest and tell them the tool supports one explicit file at a time.
