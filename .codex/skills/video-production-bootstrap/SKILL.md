---
name: video-production-bootstrap
description: Initialize and inspect a cloned Video Workshop repository so local private workspace data, production ledgers, and the Daily Engineering Loop are ready without publishing personal data.
---

# Video Production Bootstrap

## Purpose

Turn a clean clone into a local working system while keeping personal content outside Git.

## Commands

Initialize the ignored local workspace:

```bash
python3 09_tools/vp.py init
```

Inspect the control plane, workspace, Loop, privacy boundary, and optional render dependencies:

```bash
python3 09_tools/vp.py doctor
```

Show the exact public read order, local overrides, and user-approved historical
content that an AI should inspect:

```bash
python3 09_tools/vp.py context
```

Both commands are idempotent. Initialization never overwrites existing ledgers, style files, dictionaries, recordings, or media.

## Private Outputs

The initializer creates local-only directories and seed files under:

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
17_reports/evolution/
```

These paths remain protected by `.gitignore`.

## First AI Read

After `init`, ask the AI to read `AGENTS.md` and run `vp context`. If historical
Inbox, Script, or Log files exist, follow `references/personalization.md` and
write the distilled style only to the local ignored override files. The
original corpus remains unchanged.

`00_state/personalization.json` starts as `pending`. It may be changed to
`ready` after the local profile and vocabulary have been generated and checked
for accidental secrets. Personalization is optional; the public default style
keeps a new workspace usable before that step.

## Daily Loop

After initialization, workflow corrections use:

```bash
python3 09_tools/vp.py observe --summary "..."
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

The default TopK is read from `00_system/evolution-policy.json` and remains locked after the first daily selection.
