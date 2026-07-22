---
name: video-production-evolution
description: Run the P0 Daily Engineering Loop for the video production system. Use when recording workflow updates, triaging observations, ranking rolling Top-K Issues, generating candidates, or producing the daily evolution report. P0 is read-only with respect to formal Skills, Rules, Hooks, Agents, and versions.
---

# Video Production Evolution

## Purpose

Provide one controlled channel for daily workflow changes:

```text
Observation -> Triage -> Deduplicate -> Issue-ready Candidate -> Rolling Top-K Issues
```

Every update is retained, but an Observation is not automatically an Issue. The current Top-K contains up to three unresolved work slots. New issue-ready observations, explicit Loop runs, and verified completions reconcile those slots immediately. Unfinished work carries across dates and is re-ranked; completing one item removes it from the active Top-K and fills the opening from ranked backlog.

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
  --source user-correction \
  --workflow-step subtitle-review \
  --reproduction "同一录音复核后字幕仍整体提前" \
  --user-impact "需要整条返工校时" \
  --impact-level high \
  --priority-reason "重复返工且影响发布" \
  --validation-plan "对齐词级时间戳并运行字幕 QC" \
  --reproducible \
  --causes-rework
```

When reproduction or impact becomes clear later, append triage without falsely counting another occurrence:

```bash
python3 09_tools/vp.py evolve triage CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD \
  --reproduction "从 review 断点恢复且 word timing 缺失" \
  --user-impact "无法继续导出" \
  --impact-level critical \
  --reproducible \
  --blocking
```

Run the deterministic Loop through `scripts/evolution_loop.py` via the CLI:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

Complete one active Top-K Issue only after verification evidence exists:

```bash
python3 09_tools/vp.py evolve complete CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD \
  --change-type feature \
  --evidence path/to/test-report.md \
  --artifact path/to/output \
  --process-action test \
  --process-note "增加字幕时间轴回归测试"
```

Completion is append-only and idempotent. It writes
`00_state/evolution/completed/YYYY-MM-DD.json`, releases the rolling Top-K slot,
and prevents the completed candidate from returning in a later Loop. A
completion becomes a Release candidate and receives a deterministic
`releaseTarget`: `bugfix` advances patch, `feature` advances minor, and
`major-evolution` stays pending user confirmation. This metadata plan never
bumps `package.json.version` or changes `activeRelease`.

Inspect or backfill the local version plan with:

```bash
python3 09_tools/vp.py release version-plan
python3 09_tools/vp.py release version-backfill --apply
```

When GitHub Issues integration is enabled, `observe`, `evolve`, and `evolve complete` immediately sync the public-safe projection. Manual reconciliation remains available:

```bash
python3 09_tools/vp.py evolve issues sync \
  --date YYYY-MM-DD \
  --if-enabled
```

Use `--dry-run` to inspect classification and privacy redactions without calling GitHub. The sync is idempotent by Candidate ID. Current slots use `status:topk`; items displaced into backlog use `status:backlog`; verified completions use `status:verified`. GitHub failure is reported but does not roll back local state or block video production.

Optional Top-K limit override:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD --top-k 5
```

The default policy uses `selection.mode=rolling`. A legacy workspace may opt into `selection.mode=frozen`; only that mode requires explicit reselection:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD --reselect
```

## Issue Readiness

Every anomaly may remain in the local Observation ledger. It becomes eligible for a Top-K Issue only when at least one condition is true:

- The behavior is reproducible.
- The same fingerprint occurred at least twice inside the lookback window.
- It blocks a usable production artifact.
- It causes material rework or has high/critical impact.
- A deterministic audit or validator marked the finding.
- The user explicitly approved a feature, policy, or permanent workflow change.

Priority alone does not promote an Observation. `P0` controls ordering after the Issue-readiness gate; it is not evidence by itself.

Unselected backlog carries into later runs. Each elapsed calendar day raises its effective priority by one level, capped at `P0`. Within the same effective priority, production blocking, impact level, material rework, and reproducibility rank before origin and age; equivalent work uses the earliest `firstSeenAt`. Other eligible updates use `parked-topk`; non-eligible updates use `needs-evidence`.

## Invariants

- Process all valid observations for the date; do not truncate collection because Top-K is small.
- Triage-only updates are append-only context and never increase `occurrenceCount`.
- Default `K=3` unless configuration or an explicit CLI flag changes it.
- Keep the active Top-K at the configured slot count and reconcile it after every supported event.
- Carry every unfinished issue-ready item across dates and re-rank it in the next round.
- Remove completed entries from active slots, preserve them in the append-only completion ledger, and refill immediately.
- Keep frozen mode available for legacy workspaces; rolling is the default.
- Re-running the same date with unchanged inputs must reuse the previous result.
- Production locks defer the Loop.
- Invalid NDJSON must not overwrite the original file or the previous successful state.
- P0 never changes published release pointers, formal Skills, Rules, Hooks, Agents, or production paths. Completion may write release-plan metadata only.

## GitHub Issue Gate

- Local Evolution state and completion ledgers remain the source of truth.
- Every active Top-K item gets an Issue. `system-core` and `content-profile` may expose their
  sanitized summaries; other scopes use a redacted title and body. Raw evidence
  is never uploaded.
- `vp evolve complete` immediately changes the Issue from `status:topk` to `status:verified`; sync never closes an Issue.
- Every Issue body includes affected step, reproduction/run context, user or artifact loss, priority reason, proposed fix, validation plan, and the process/gate feedback decision.
- A PR that uses `Closes #N` for a Top-K Issue must pass
  `vp evolve issues check-pr --repo OWNER/REPO --pr N`.
- GitHub closes a verified Issue only after the linked PR merges into the
  repository default branch.

### Executing a Top-K Issue

An Issue is not complete when it is visible or when local completion changes its
label to `status:verified`. Start the bounded repair task first:

```bash
python3 09_tools/vp.py evolve issues start CAND-ID \
  --date YYYY-MM-DD --repo OWNER/REPO --json
git switch -c fix/topk-cand-id
```

Implement the smallest fix, add regression coverage, and then record evidence:

```bash
python3 09_tools/vp.py evolve complete CAND-ID \
  --date YYYY-MM-DD --change-type bugfix \
  --evidence path/to/test-report.md --process-action test
python3 09_tools/vp.py evolve issues check-pr \
  --repo OWNER/REPO --pr N --require-topk
python3 09_tools/vp.py evolve issues merge \
  --repo OWNER/REPO --pr N --apply --auto
```

The PR must target `main`, be Ready for review, retain the generated `Closes #N`,
and pass required checks. The repository `topk-merge` workflow only handles
same-repository `fix/topk-*` branches and never checks out or executes PR code.
It queues GitHub auto-merge; GitHub closes the Issue only after the PR reaches
the default branch. Do not run the repair loop during an active production lock.

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
- Issue-ready blockers participate in the rolling Top-K after production locks clear.
- Keep the raw production issue list local. Non-public Top-K candidates use a
  redacted GitHub Issue projection.

## Outputs

```text
00_state/evolution/YYYY-MM-DD.json
17_reports/evolution/YYYY-MM-DD-daily-evolution.md
```

The daily report includes a `生产问题清单` view derived from production-related
Observations. It also includes a separate completed-candidate view sourced from
the append-only completion ledger, so historical completed work is not confused
with active Top-K or backlog work. `needs-evidence` means triage is still pending;
`parked-topk` means the issue is confirmed but waiting for a later engineering
round.

Error report:

```text
17_reports/evolution/YYYY-MM-DD-daily-evolution-error.md
```
