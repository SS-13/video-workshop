# Video Workshop

A local-first framework that turns everyday ideas and recordings into a
reviewed video, consistent cover pair, accurate subtitles, and a publish-ready
package.

The repository contains the reusable production system. Personal content and
media stay on the local machine.

## What It Covers

- raw idea intake and teleprompter script writing;
- input and output compliance review;
- 3:4 and 4:3 covers from one locked design route;
- real-audio transcription, dictionary correction, and timing QC;
- one combined cover/SRT review gate;
- one-pass final rendering with optional confirmed inserts;
- publish title, description, chapters, and production metrics;
- Observation -> TopK -> Daily Engineering Loop;
- stable v2 production with a preserved legacy fallback.

## Quick Start

```bash
git clone https://github.com/SS-13/video-workshop.git
cd video-workshop
python3 -m pip install -r requirements.txt
npm run setup
npm run context
npm run doctor
```

Then tell the local AI:

```text
Read AGENTS.md and the files reported by npm run context. If local historical
content exists, personalize the ignored local profile without changing source
files. Then prepare today's video-diary workspace.
```

The first new video diary starts at `Day 1`. Set a different baseline with
`VIDEO_DIARY_START_DAY` or `npm run new-day -- YYYY-MM-DD --day N`.

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

## Local Personalization

`npm run setup` creates ignored local files for speaking style, proper nouns,
subtitle corrections, ledgers, and Loop state. `npm run context` tells the AI
exactly which public files and user-approved local corpus files to read.

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
python3 09_tools/vp.py observe --summary "subtitle was early" --priority P1
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

All observations are retained. At most three enter the first locked TopK for a
day. The Loop proposes candidates; it does not silently rewrite the system.

## Requirements

- Python 3.10+
- Node.js 20 (see `.nvmrc`)
- FFmpeg and FFprobe for rendering
- Pillow for cover rendering
- a CJK font; set `VIDEO_WORKSHOP_FONT` when no supported system font exists
- whisper.cpp or OpenAI Whisper for transcription

`npm run doctor` separates required control-plane failures from optional render
dependency warnings.

Optional tool and Feishu overrides are documented in `.env.example`. Keep the
real `.env` local; it is ignored by Git.

## Documentation

- [AGENTS.md](AGENTS.md): canonical AI operating rules
- [START_HERE.md](START_HERE.md): first clone and first video
- [PIPELINE.md](PIPELINE.md): system and artifact map
- [WORKFLOW.md](WORKFLOW.md): current 3.0 production workflow
- [.codex/agents/README.md](.codex/agents/README.md): Agent ownership
- [CONTRIBUTING.md](CONTRIBUTING.md): PR scope, tests, and privacy rules

## Privacy

The default `.gitignore` excludes raw ideas, scripts, media, exports, browser
sessions, credentials, personal style, dictionaries, logs, reports, runtime
state, and generated cover galleries. Review staged files before every public
push.

## License

[MIT](LICENSE)
