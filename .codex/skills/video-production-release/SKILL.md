---
name: video-production-release
description: Manage Candidate, Shadow, Canary, activation, and rollback gates for the video production system without modifying production media. Use for 3.0 release status, real-video Canary adoption, release readiness, activation, and rollback.
---

# Video Production Release

## Purpose

Provide the guarded release path:

```text
Candidate -> Shadow -> Real Canary -> User Approval -> Active
```

This skill manages metadata, Run state, evidence, and Release pointers. It never edits, re-encodes, moves, replaces, or deletes source recordings, subtitles, covers, or final videos.

## References

Read before a release action:

```text
00_system/release-policy.json
00_system/releases/3.0.0/manifest.json
00_system/releases/3.0.0/rollback.yaml
17_reports/releases/3.0.0/CANARY_RUNBOOK.md
```

## Commands

Inspect status and readiness:

```bash
python3 09_tools/vp.py release status
python3 09_tools/vp.py release readiness
```

Adopt one completed Stable production without re-encoding media:

```bash
python3 09_tools/vp.py release canary-adopt --date YYYY-MM-DD
```

Validate and record the real Canary gate:

```bash
python3 09_tools/vp.py release canary-check --run-id RUN_ID
python3 09_tools/vp.py release canary-check --run-id RUN_ID --record-pass
```

Activation and rollback:

```bash
python3 09_tools/vp.py release activate --dry-run
python3 09_tools/vp.py release activate --confirm --actor user
python3 09_tools/vp.py release rollback --confirm --actor user
```

After 3.x is Active, `publish:package` automatically invokes the dormant-safe Run finalizer. It can also be run explicitly:

```bash
python3 09_tools/vp.py run finalize-active --date YYYY-MM-DD
```

## Guardrails

- Keep `2.1.0` Active until the real Canary passes and the user explicitly approves activation.
- Do not run Candidate encoding while the Stable production task is encoding.
- `canary-adopt` may write only Candidate metadata and `00_state/runs`; it must preserve Stable package and media bytes.
- Never record a Canary pass when `publishReady`, subtitle QC, compliance, production statistics, cover ratios, or required artifact paths fail.
- Never use a Shadow package as real Canary evidence.
- Rollback changes only Release pointers and version metadata; retain all evidence.
- The Active Run hook must return `enabled=false` and perform no writes while `2.1.0` is Active.
- Do not bulk delete.

## Handoff

Return:

```text
active_release
candidate_release
run_id
canary_valid
recorded
blocking_gates
next_command
```
