---
name: video-production-evolution
description: Run the P0 Daily Engineering Loop for the video production system. Use when recording workflow updates, collecting user corrections, ranking the daily TopK, generating candidates, or producing the daily evolution report. P0 is read-only with respect to formal Skills, Rules, Hooks, Agents, and versions.
---

# Video Production Evolution

## Purpose

Provide one controlled channel for daily workflow changes:

```text
Observation -> Normalize -> Deduplicate -> Candidate -> TopK -> Daily Report
```

Every update is retained. Only the daily TopK is selected for the candidate update list. `K` defaults to `3` in `00_system/evolution-policy.json`.

## Commands

Record one observation with `09_tools/vp.py`:

```bash
python3 09_tools/vp.py observe \
  --date YYYY-MM-DD \
  --summary "字幕整体偏快" \
  --category subtitle-rule \
  --priority P1 \
  --scope system-core \
  --component subtitle-timing \
  --source user-correction
```

Run the deterministic Loop through `scripts/evolution_loop.py` via the CLI:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

Complete one locked TopK item only after verification evidence exists:

```bash
python3 09_tools/vp.py evolve complete CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD \
  --change-type feature \
  --evidence path/to/test-report.md \
  --artifact path/to/output
```

Completion is append-only and idempotent. It writes
`00_state/evolution/completed/YYYY-MM-DD.json`, keeps the daily TopK locked,
and prevents the completed candidate from returning in a later Loop. A
completion becomes a Release candidate, but it does not choose a target
version, bump a version, or change `activeRelease`.

After the nightly Loop, sync the public-safe TopK projection:

```bash
python3 09_tools/vp.py evolve issues sync \
  --date YYYY-MM-DD \
  --if-enabled
```

Use `--dry-run` to inspect classification and privacy redactions without calling
GitHub. The sync is idempotent by Candidate ID. It creates at most one Issue per
candidate, applies one `type:bug|feature|other` label, and replaces the previous
priority label as aging raises `P3 -> P2 -> P1 -> P0`. Open managed Issues keep
aging even when they are absent from the next day's TopK.

Optional TopK override:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD --top-k 5
```

The first successful selection for a date is frozen. Later observations remain eligible for deduplication and backlog ranking without replacing the day's plan. Only use explicit reselection for an approved blocking production issue:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD --reselect
```

## Candidate Eligibility

An update is eligible when at least one condition is true:

- The user explicitly requested promotion or permanent behavior.
- The same fingerprint occurred at least twice inside the lookback window.
- Priority is `P0`.
- A deterministic audit or validator marked the finding.

Unselected backlog carries into later daily runs. Each elapsed calendar day raises its effective priority by one level, capped at `P0`. Selection always processes effective `P0` before lower priorities; P0 ties use the earliest `firstSeenAt` first. After priority, explicit promotion, deterministic evidence, occurrence count, and recency break ties. The first K become the daily TopK. Other eligible updates use `parked-topk`; non-eligible updates use `needs-evidence`.

## Invariants

- Process all valid observations for the date; do not truncate collection because TopK is small.
- Default `K=3` unless configuration or an explicit CLI flag changes it.
- Freeze the first daily TopK while allowing unlimited append-only observations.
- Age only carried backlog; an item already selected into a prior TopK does not automatically repeat the next day.
- Keep completed TopK entries visible as `completed`; never return them to Candidate or backlog.
- Require explicit `--reselect` to replace an already selected daily item.
- Re-running the same date with unchanged inputs must reuse the previous result.
- Production locks defer the Loop.
- Invalid NDJSON must not overwrite the original file or the previous successful state.
- P0 never modifies formal Skills, Rules, Hooks, Agents, production scripts, or versions.

## GitHub Issue Gate

- Local Evolution state and completion ledgers remain the source of truth.
- Every TopK gets an Issue. `system-core` and `content-profile` may expose their
  sanitized summaries; other scopes use a redacted title and body. Raw evidence
  is never uploaded.
- `vp evolve complete` plus the next sync changes the Issue from
  `status:topk` to `status:verified`; sync never closes an Issue.
- A PR that uses `Closes #N` for a TopK Issue must pass
  `vp evolve issues check-pr --repo OWNER/REPO --pr N`.
- GitHub closes a verified Issue only after the linked PR merges into the
  repository default branch.

## Production Issue Loop

Use the existing Observation ledger as the single source of truth for production
blockers. Do not create a second issue database.

```text
blocker -> Observation -> finish through stable workaround/fallback
        -> post-run triage -> confirmed fix candidate -> next Engineering Loop
```

- First occurrence: record symptom, stage, impact, evidence, and workaround;
  normally omit `--promote`.
- After production: classify transient/input/operator/system causes.
- Confirmed system defect: add reproducible evidence and `--promote`.
- Existing locked TopK remains unchanged unless a P0 failure blocks Stable.
- Keep the raw production issue list local. Non-public TopK candidates use a
  redacted GitHub Issue projection.

## Outputs

```text
00_state/evolution/YYYY-MM-DD.json
17_reports/evolution/YYYY-MM-DD-daily-evolution.md
```

The daily report includes a `生产问题清单` view derived from production-related
Observations. `needs-evidence` means triage is still pending; `parked-topk` means
the issue is confirmed but waiting for a later engineering round.

Error report:

```text
17_reports/evolution/YYYY-MM-DD-daily-evolution-error.md
```
