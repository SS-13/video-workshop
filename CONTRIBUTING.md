# Contributing

Video Workshop accepts focused fixes to production reliability, subtitle
accuracy, cover consistency, portability, privacy, and the Daily Engineering
Loop.

## Before Opening a PR

1. Read `AGENTS.md` and `PIPELINE.md`.
2. Keep personal content and generated media out of the change.
3. Preserve `edit:render-day-legacy` when changing the v2 route.
4. Add or update a deterministic test for behavior changes.
5. Run:

```bash
python3 -m unittest discover -s 09_tools/tests -p 'test_*.py'
python3 -m unittest discover -s .codex/skills/video-diary-edit/tests -p 'test_*.py'
python3 -m unittest discover -s .codex/skills/video-production-evolution/tests -p 'test_*.py'
python3 09_tools/vp.py registry validate
python3 09_tools/vp.py contract validate
```

## Privacy Rules

Do not include:

- raw ideas, scripts, recordings, exports, or personal logs;
- personal speaking-style profiles or vocabulary dictionaries;
- credentials, cookies, browser profiles, QR codes, or local `.env` files;
- absolute home-directory paths;
- unlicensed font files;
- generated media used only for local verification.

Use small synthetic fixtures. If a media fixture is essential, keep it minimal,
review its contents, and place it under an explicitly allowed `tests/fixtures/`
path.

## Pull Request Scope

Prefer one behavioral change per PR. Describe:

- the production problem;
- the changed invariant or command;
- tests and clean-clone evidence;
- stable-channel and rollback impact;
- any new local data that must remain ignored.

Changes to release activation, privacy boundaries, or destructive file handling
require explicit maintainer review.
