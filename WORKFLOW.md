# Video Workshop 3.0 Workflow

## Objective

Produce a daily talking-head video with accurate subtitles and a consistent
cover while minimizing repeated transcription, repeated encoding, manual file
search, and model token use.

The default route is `video-diary`. Other content types are explicit opt-ins.

## Stage 0: Workspace Readiness

On a clean clone:

```bash
npm run setup
npm run context
npm run doctor
```

The AI reads `AGENTS.md` first. If historical content is present and approved,
it follows the personalization protocol and writes only ignored local overrides.

## Stage 1: Intake

Before writing today's idea:

```bash
npm run new-day -- YYYY-MM-DD
```

Write the raw wording to `01_inbox/YYYY-MM-DD.md`. The Inbox is evidence and is
never summarized or rewritten in place.

Run a lightweight input compliance review. Mark risky claims, advertising-law
language, insults, prohibited content, and external-app download or diversion
language. Apply the smallest safe rewrite only to the script, not the Inbox.

## Stage 2: Script

Use these style layers in order:

1. today's raw idea and explicit user corrections;
2. local `10_skills/personal-speaking-style/SKILL.md` when personalized;
3. public `00_system/defaults/speaking-style.md`;
4. script Skill rules.

Write `02_scripts/YYYY-MM-DD.md`. Keep facts and reasoning order, use speakable
sentences, and avoid generic marketing hooks. Stop here until the user has
recorded and explicitly requests editing.

## Stage 3: Source Recording

The user places source media in:

```text
03_recordings/YYYY-MM-DD/
```

Rules:

- never overwrite or move original recordings;
- inspect the source once and cache metadata/audio;
- trim only copied working media;
- remove spoken filler audio only when explicitly requested by the selected
  mode;
- the recording, not the script, is subtitle truth.

## Stage 4: Parallel Review Lanes

### Lane A: Cover

Use Pencil only when designing a new visual style, then register that approved
style as an immutable version with `vp cover design`. For daily production,
use `vp cover make` to generate the locked 3:4 and 4:3 pair from one
title/subtitle/style version. Run font, clipping, safe-area, dimension, and
consistency checks, then archive both local revisions automatically. Use
`vp cover history` to inspect style versions and recent revisions.

### Lane B: Subtitle

1. trim terminal black/watermark content from a working copy;
2. cache 16 kHz audio;
3. transcribe once with word timestamps;
4. use the current script only as bounded vocabulary context;
5. apply the local correction dictionary first, then public defaults;
6. create a corrected external SRT;
7. run text QC and word-timing/audio-alignment QC;
8. report low-confidence ranges for targeted review.

Subtitle rules:

- real spoken wording wins over the script;
- maximum two visual lines;
- clear, stable subtitles inside the safe area;
- do not shift cue timing merely to improve reading rhythm;
- fix only low-confidence ranges instead of rerunning the whole video with a
  larger model whenever possible.

## Stage 5: Combined Review Gate

Create `04_videos/YYYY-MM-DD/REVIEW.md` containing:

- 3:4 cover;
- 4:3 cover;
- corrected external SRT and preview input;
- low-confidence subtitle ranges;
- text and timing QC results;
- image/video insert plan, including exact time ranges and dimensions.

This is the default single user confirmation. Before confirmation, preprocessing
and subtitle checks may run, but final subtitle burn-in and inserts may not.

## Stage 6: Compliance and One Render

Run the output compliance review against the confirmed SRT, title, description,
and insert plan. If the result is `revise`, update text/SRT/plan only and rerun
the relevant gate.

After a pass:

1. burn confirmed subtitles;
2. add the optional one-second cover card;
3. add only confirmed inserts within video duration;
4. preserve original audio unless BGM was explicitly requested;
5. encode once;
6. run duration, stream, subtitle-safe-area, and file-integrity QC.

Default command path:

```bash
npm run edit:render-day-v2 -- --date YYYY-MM-DD --model base --stop-after-review
npm run edit:render-day-v2 -- --date YYYY-MM-DD --from-stage review --confirmed
```

Immediate fallback:

```bash
npm run edit:render-day-legacy -- --date YYYY-MM-DD --mode standard
```

Never delete the legacy route during a v2 rollout.

## Stage 7: Publish Package

The final export folder must contain:

```text
05_exports/YYYY-MM-DD/
├── *_video-diary.mp4
├── *_cover_3x4.jpg
├── *_cover_4x3.jpg
├── PUBLISH.md
└── publish-package.json
```

Generate from the corrected real-audio transcript:

- one publish title;
- one concise description;
- 3-5 chapters in `MM:SS｜标题` form;
- actual duration, file size, production time, QC status, and paths.

Record the run in `00_state/production-stats.csv` on the same day. Completion is
not reached until the user receives the publish copy and production result.

## Stage 8: Production Issues And Evolution

When a production blocker appears, record it immediately as an Observation with
the stage, impact, evidence, temporary workaround, and content ID. Keep the
current video on the stable path; use the preserved fallback instead of changing
production code mid-run.

After the video and publish package are complete:

1. classify the blocker as transient environment, source/input, operator, or
   reproducible system defect;
2. leave uncertain items as `needs-evidence`;
3. add evidence and promote confirmed system defects;
4. run the next Daily Engineering Loop only after production locks are gone;
5. keep an already locked TopK unchanged unless a P0 issue blocks Stable.

The daily evolution report generates one local `生产问题清单` from these
Observations. It is a view, not a duplicate issue ledger.

Every reusable correction may become an Observation:

```bash
python3 09_tools/vp.py observe --summary "..." --category content-rule --priority P2
```

When no production lock exists:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

The first daily TopK uses the configured limit of three and remains frozen.
Further observations stay in backlog. Candidate implementation, testing, release
activation, and rollback are separate reviewed actions.

## Stop and Safety Rules

- Do not advance from script to editing without an explicit request.
- Do not burn subtitles before the combined review gate.
- Do not modify the stable production path during an active render.
- Do not commit ignored personal data.
- Do not bulk-delete files or directories.
