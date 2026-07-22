# Video Workshop

A local-first framework that turns everyday ideas and recordings into a
reviewed video, consistent cover pair, accurate subtitles, and a publish-ready
package.

The repository contains the reusable production system. Personal content and
media stay on the local machine.

[简体中文 README](README.zh-CN.md)

## What It Covers

- raw idea intake and teleprompter script writing;
- input and output compliance review;
- 3:4 and 4:3 covers from one locked design route;
- real-audio transcription, dictionary correction, and timing QC;
- one combined cover/SRT review gate;
- one-pass final rendering with optional confirmed inserts;
- publish title, description, chapters, and production metrics;
- Observation -> Top-K Issues -> Daily Engineering Loop;
- stable v2 production with a preserved legacy fallback.

## AI Agent Bootstrap Contract

An AI Agent setting up this repository owns the bootstrap end to end. It should
detect the host environment, install only missing dependencies, verify them,
ask the user for the initial workflow choices, and initialize the workspace.
Do not ask the user to create ignored directories by hand.

Do not start content production until both dependency and workspace readiness
gates below pass. Follow the host's approval rules before installing system
packages, downloading a transcription model, or using administrator access.

### 1. Required Dependencies

| Dependency | Minimum | Purpose |
| --- | --- | --- |
| Git | current supported release | clone, updates, rollback |
| Python | 3.10+ | control plane, cover and subtitle tools |
| Node.js + npm | Node 20+ | project commands and JavaScript helpers |
| FFmpeg + FFprobe | build with `ass`, `subtitles`, and `drawtext` filters | audio extraction, subtitles, final render |
| Pillow | version from `requirements.txt` | cover rendering |
| fontTools | version from `requirements.txt` | verify selected font glyph coverage |
| CJK font | one readable Chinese font | Chinese covers and subtitles |
| Local speech-to-text | `whisper.cpp` plus a GGML model, or OpenAI Whisper | real-audio transcription and timing |

Recommended transcription route: `whisper.cpp` with `ggml-base.bin`. OpenAI
Whisper is the supported fallback. Git, Python, Node, FFmpeg, a CJK font, and
one transcription route are required before the first real video.

### 2. Detect and Install Missing Tools

Inspect first:

```bash
git --version
python3 --version
node --version
npm --version
ffmpeg -version
ffprobe -version
whisper-cli --help
whisper --help
```

Install only what is missing. Typical macOS commands are:

```bash
brew install git python node ffmpeg whisper-cpp
```

Typical Debian/Ubuntu commands are:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-pip nodejs npm ffmpeg fonts-noto-cjk
```

Use an official Node installer or version manager when the Linux package
manager provides Node older than version 20. Typical Windows PowerShell
commands are:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Gyan.FFmpeg -e
```

On Windows, verify that `python3` resolves to Python 3.10 or newer because the
current npm scripts invoke that command name.

For the recommended `whisper.cpp` route on macOS/Linux, install the base model
at the default path:

```bash
mkdir -p "$HOME/.cache/whisper.cpp"
curl -L \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin \
  -o "$HOME/.cache/whisper.cpp/ggml-base.bin"
```

When `whisper.cpp` is unavailable, install the fallback instead:

```bash
python3 -m pip install -U openai-whisper
```

Then clone the repository and install its Python dependencies:

```bash
git clone https://github.com/SS-13/video-workshop.git
cd video-workshop
python3 -m pip install -r requirements.txt
```

Run the deterministic media dependency gate:

```bash
npm run edit:deps
```

The gate must finish with `SUMMARY ok`. If it reports a missing FFmpeg filter,
transcription binary, or model, the Agent resolves that item and reruns the
check before continuing. CJK font readiness is checked by `npm run doctor`
after initialization.

### 3. User Configuration Checkpoint

Before initialization, the Agent asks the user to confirm:

1. content type: `video-diary` by default, or another registered type shown by
   `python3 09_tools/vp.py content-type list`;
2. publishing preset: the current built-in preset is Douyin;
3. cover outputs: the current built-in pair is `3:4` and `4:3`;
4. video-diary Day baseline: start at Day 1 or import an existing Day number;
5. personalization: use public defaults now, or learn from user-approved local
   Inbox, Script, and Log history after initialization.

The Agent reports the selected values back and waits for confirmation before
running setup.

When a command omits the content date, the local content day changes at 09:00:
inputs before 09:00 use the previous date. An explicit `--date` always wins.

Only offer values the installed renderer supports. If the user requests a
different platform or cover ratio, retain it as an adapter requirement and do
not claim the default renderer can already produce it.

### 4. Initialize and Verify

After the user confirms the setup choices:

```bash
npm run setup
npm run doctor
npm run context
```

`setup` creates every required ignored directory and local seed file without
overwriting existing content. The readiness gate is:

```text
valid=true
ready_for_content=true
ready_for_render=true
loop_ready=true
```

The Agent fixes any failed required check before proceeding. Optional local
history may then be distilled according to the personalization protocol shown
by `npm run context`.

### 5. Start the First Idea and Recording

Initialize the date, using the Day baseline confirmed above:

```bash
npm run new-day -- YYYY-MM-DD
# Existing series only:
npm run new-day -- YYYY-MM-DD --day 42
```

The user can now send a raw idea. The Agent preserves it in `01_inbox/`, runs
input compliance review, and writes the recording script to `02_scripts/` when
asked. After the user places the real recording in
`03_recordings/YYYY-MM-DD/video-diary/001/`, transcription can start directly:

```bash
npm run subtitle:transcribe -- \
  --date YYYY-MM-DD \
  --content-type video-diary \
  --sequence 001 \
  --engine auto \
  --model base \
  --word-timestamps
```

For the normal video-diary route, the Agent can build the cover and corrected
external SRT review pack together:

```bash
npm run edit:render-day-v2 -- --date YYYY-MM-DD --model base --stop-after-review
```

The recording is subtitle truth. The script is context only.

The same command also creates a local browser-review folder next to `REVIEW.md`:

```text
04_videos/YYYY-MM-DD/video-diary/001/review/
├── video.mp4       # relative link to the review video
└── subtitles.srt   # relative link to the corrected external SRT
```

Choose these two files from the same folder in the browser subtitle tool. They
are links, not copies, so this convenience entry does not duplicate video data.

Then tell the local AI:

```text
Read AGENTS.md and the files reported by npm run context. If local historical
content exists, personalize the ignored local profile without changing source
files. Then prepare today's video-diary workspace.
```

## Daily Flow

```text
idea -> compliance -> script -> recording
     -> cover lane + subtitle lane
     -> combined review -> compliance -> one render
     -> publish package -> metrics -> Observation/Loop
```

Start a date:

```bash
npm run new-day -- YYYY-MM-DD
```

Build the cover/SRT review pack after a recording is present:

```bash
npm run edit:render-day-v2 -- --date YYYY-MM-DD --model base --stop-after-review
```

Continue after review:

```bash
npm run edit:render-day-v2 -- --date YYYY-MM-DD --from-stage review --confirmed
```

Fallback:

```bash
npm run edit:render-day-legacy -- --date YYYY-MM-DD --mode standard
```

## Local Media Retention

Retention is disabled on a fresh clone. After explicit local opt-in, a
three-day window keeps today and the previous two dates. Older video media is
eligible only when its content item has a publish-ready package and a matching
production-statistics row.

```bash
npm run cleanup -- configure --enabled --days 3
npm run cleanup -- status --date YYYY-MM-DD
npm run cleanup -- run --date YYYY-MM-DD
npm run cleanup -- run --date YYYY-MM-DD --apply --if-enabled
```

The runner skips while production is locked. It deletes no directories and
preserves scripts, subtitles, covers, publish copy, JSON, statistics, and Run
State. Every exact deleted path is appended to the local retention ledger.
Doctor and the shared v2/legacy render entrypoint also refuse to render below
the configured free-space threshold.

## Cover Design System

Cover design stays inside the existing `video-diary-cover` Skill. Pencil is
used only when the visual system changes; approved styles become immutable
versions that the fast daily renderer can reuse.

The public CLI has three cover actions:

```bash
# Register an approved Pencil design and its 3:4 / 4:3 previews
npm run cover -- design --help

# Generate, QC, lock, and archive today's cover pair
npm run cover -- make --help

# Inspect style versions and recent daily revisions
npm run cover -- history --route video-diary
```

Pencil sources and personal preview assets remain under ignored local cover
history. Renderer tokens live in the versioned route configuration. Existing
low-level render, HTML-export, archive, and gallery scripts remain available as
compatibility internals, so the daily workflow only needs the three actions
above.

## Local Personalization

`npm run setup` creates the complete ignored local workspace, including
production, template, research, report, learning, speaking-style, vocabulary,
ledger, and Loop paths. Existing local files are never overwritten.
`npm run context` tells the AI exactly which public files and user-approved
local corpus files to read.

The AI distills stable patterns into:

```text
10_skills/personal-speaking-style/SKILL.md
11_templates/关键词收集/字幕纠错词库.tsv
11_templates/关键词收集/专有名词清单.md
00_state/personalization.json
```

These files never need to enter the public repository.

## Daily Evolution

```bash
python3 09_tools/vp.py observe --summary "subtitle was early" --priority P1 \
  --workflow-step subtitle-review --reproducible --causes-rework
python3 09_tools/vp.py evolve triage CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD --reproduction "resume without word timing" --blocking
python3 09_tools/vp.py evolve --date YYYY-MM-DD
python3 09_tools/vp.py evolve complete CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD \
  --change-type feature \
  --evidence path/to/test-report.md \
  --process-action test
python3 09_tools/vp.py evolve issues sync \
  --date YYYY-MM-DD \
  --if-enabled

# Inspect and backfill release targets for completed Bug/Feature work
python3 09_tools/vp.py release version-plan
python3 09_tools/vp.py release version-backfill --apply
python3 09_tools/vp.py release status
```

All observations are retained, but they do not automatically become Issues. By
default, three unresolved work slots form a rolling Top-K. Reproducible,
repeated, blocking, high-impact, material-rework, deterministic, or explicitly
approved work may cross the Issue-readiness gate. Priority only orders work
after that gate. New eligible work is reconciled immediately; unfinished work
carries across dates, and a verified completion releases its slot and refills it
from backlog. Completions enter an append-only local ledger and receive a
deterministic `releaseTarget`: `bugfix` advances the patch number, `feature`
advances the minor number, and `major-evolution` remains pending user
confirmation. The plan never changes `activeRelease` or `package.json.version`;
Canary, release verification, and explicit activation remain separate gates.
The implementation, contract, tests, and CLI are public, while real completion
evidence remains local.

The optional GitHub projection is reconciled after `observe`, `evolve`, and
verified completion. It creates one Issue per active Top-K candidate.
Issue-ready candidates outside the active slots are also projected with
`status:backlog`, so the public queue retains the work that will refill a slot.
Each Issue includes the affected workflow step, reproduction/run context, user
or artifact loss, priority reason, proposed fix, validation plan, and process or
gate feedback decision.
Public-safe summaries become the title without a Top-K prefix; private scopes use
a redacted projection. Labels classify `bug`, `feature`, or `other`; the single priority
label is replaced as aging raises `P3 -> P2 -> P1 -> P0`. Active, displaced,
and completed work uses `status:topk`, `status:backlog`, and `status:verified`.
A linked PR uses `Closes #N`, and GitHub closes it only after the verified PR
merges into the default branch.

GitHub Issues are an execution queue, not the end of the workflow. Every active
Top-K item follows this loop:

```bash
# Resolve the active candidate into an Issue, branch, PR body, and completion command
python3 09_tools/vp.py evolve issues start CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD --repo OWNER/REPO --json

# Create the suggested repair branch, for example:
git switch -c fix/topk-cand-xxxxxxxxxxxx

# Implement the smallest fix and add a regression test.
# Record evidence only after the verification is available.
python3 09_tools/vp.py evolve complete CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD --change-type bugfix \
  --evidence path/to/test-report.md --process-action test

# The PR must keep the generated Closes #N reference.
python3 09_tools/vp.py evolve issues check-pr \
  --repo OWNER/REPO --pr N --require-topk

# Verify required checks and queue GitHub auto-merge.
python3 09_tools/vp.py evolve issues merge \
  --repo OWNER/REPO --pr N --apply --auto
```

`issues start` does not edit production code; it gives an Agent a bounded repair
task. Top-K repair branches use `fix/topk-<candidate-id>`. A repair PR must target
`main`, be Ready for review, reference a verified Top-K Issue, and pass all required
checks. `.github/workflows/topk-merge.yml` enables auto-merge only for same-repository
Top-K repair branches and never executes PR branch code. After the PR reaches `main`,
its trusted post-merge job (covering both PR-close and successful-test fallback paths)
closes only referenced Issues that still have both `topk`
and `status:verified`; Fork PRs, ordinary PRs, and unverified Issues are left alone.

To inspect or compensate for one already merged repair PR, preview the post-merge
reconciliation first and add `--apply` only after the target is confirmed:

```bash
python3 09_tools/vp.py evolve issues reconcile --repo OWNER/REPO --pr N
python3 09_tools/vp.py evolve issues reconcile --repo OWNER/REPO --pr N --apply
```

## Optional Integrations

Optional rendering paths, Feishu intake, Douyin metrics, Chrome, and local tool
overrides are documented in `.env.example`. Set `VIDEO_WORKSHOP_FONT` when no
supported system CJK font is available. Keep the real `.env` local; it is
ignored by Git.

## Documentation

- [AGENTS.md](AGENTS.md): canonical AI operating rules
- [START_HERE.md](START_HERE.md): first clone and first video
- [PIPELINE.md](PIPELINE.md): system and artifact map
- [WORKFLOW.md](WORKFLOW.md): current 3.0 production workflow
- [MIGRATION.md](MIGRATION.md): date-first workspace migration and recovery
- [MIGRATION.zh-CN.md](MIGRATION.zh-CN.md): 中文迁移与恢复说明
- [.codex/agents/README.md](.codex/agents/README.md): Agent ownership
- [CONTRIBUTING.md](CONTRIBUTING.md): PR scope, tests, and privacy rules

## Privacy

The default `.gitignore` excludes raw ideas, scripts, media, exports, browser
sessions, credentials, personal style, dictionaries, logs, reports, runtime
state, and generated cover galleries. Review staged files before every public
push.

## License

[MIT](LICENSE)
