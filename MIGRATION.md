# Date-First Layout Migration

[简体中文](MIGRATION.zh-CN.md)

Use this guide when an existing local workspace still stores content directly
under `YYYY-MM-DD` and needs the current date/content-type/sequence layout.

```text
YYYY-MM-DD/<content-type>/<sequence>
```

The default historical classification is `video-diary/001`.

## Before You Start

- Finish or stop active video production. Do not migrate during rendering.
- Make a filesystem backup or snapshot of ignored local workspace data. Git
  cannot restore private content because these paths are intentionally ignored.
- Keep the original recording directories until the migrated workspace has
  passed verification.

Back up at least:

```text
00_state/
01_inbox/
02_scripts/
03_recordings/
04_videos/
05_exports/
06_logs/
15_cover_gallery/
```

## Preview

The command is a dry run unless `--apply` is present:

```bash
python3 09_tools/migrate-date-first-layout.py \
  --root . \
  --report 17_reports/migrations/date-first-dry-run.json
```

Review the report before continuing. The command stops before applying changes
when a target already contains different content.

## Apply

```bash
python3 09_tools/migrate-date-first-layout.py \
  --root . \
  --apply \
  --report 17_reports/migrations/date-first-apply.json
```

Original recordings under `03_recordings/` are preserved and linked or copied
into the new layout. Text files and derived media may be moved, so the backup is
the recovery source for those paths.

## Verify

```bash
npm run doctor
npm run new-day -- 2030-01-01
python3 09_tools/vp.py registry validate
python3 09_tools/vp.py contract validate
```

Check that existing content resolves under the new layout and that Stable v2
and legacy rendering commands remain registered.

## Recovery

There is no automatic reverse migration. If verification fails:

1. Stop production and retain the migration reports.
2. Restore moved text and derived-media paths from the filesystem backup.
3. Keep original recordings unchanged.
4. Return to the previous known-good framework commit or release.
5. Run `npm run doctor` before resuming production.

The legacy renderer is an encoding/workflow fallback; it is not a directory
rollback mechanism.
