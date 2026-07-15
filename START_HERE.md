# Start Here

An AI Agent must complete the dependency installation and user configuration
checkpoint in `README.md` before running initialization. Do not begin with a
partial media toolchain: `npm run edit:deps` must report `SUMMARY ok`.

## 1. Initialize a Clone

```bash
python3 -m pip install -r requirements.txt
npm run setup
npm run context
npm run doctor
```

`setup` is idempotent. It creates ignored local workspaces, ledgers, a private
style override, a private vocabulary library, personalization state, and the
Daily Engineering Loop directories. Existing files are never overwritten.

This includes the production folders, cover/audio template folders, research,
predictions, learning archives, and audit/evolution/release report folders that
are intentionally absent from Git. A clean clone does not require any manual
directory setup.

## 2. Let the AI Learn Local Content Once

Ask the AI to read `AGENTS.md`, run `npm run context`, and follow the listed
order. If historical Inbox, Script, or Log files exist, the command reports all
of them.

The AI may analyze those user-approved files and update only:

```text
10_skills/personal-speaking-style/SKILL.md
11_templates/关键词收集/字幕纠错词库.tsv
11_templates/关键词收集/专有名词清单.md
00_state/personalization.json
```

The history stays unchanged. If there is no history, the public default style
is enough to start.

## 3. Start Today's Content

```bash
npm run new-day -- YYYY-MM-DD
```

This creates the local date workspace and increments the video-diary Day number.
A clean clone starts from Day 1. Override only when importing an existing series:

```bash
npm run new-day -- YYYY-MM-DD --day 42
```

Send the raw idea to the AI. It preserves the source in `01_inbox/`, runs the
input compliance check, writes a script to `02_scripts/`, and stops.

## 4. Add the Recording

Put the original file in:

```text
03_recordings/YYYY-MM-DD/video-diary/001/
```

The filename may remain unchanged. Tell the AI that the video is uploaded and
ask it to create the combined cover/SRT review pack.

The default v2 route:

1. inspects the recording once;
2. builds 3:4 and 4:3 covers;
3. transcribes the real audio with word timing;
4. applies public defaults plus the local correction dictionary;
5. checks subtitle text and timing;
6. returns one review pack before final rendering.

## 5. Confirm Once, Then Export

After the cover pair, external SRT, and insert plan are confirmed, the system
runs compliance review and one final render. The export directory contains:

```text
05_exports/YYYY-MM-DD/video-diary/001/
├── *_video-diary.mp4
├── *_cover_3x4.jpg
├── *_cover_4x3.jpg
├── PUBLISH.md
└── publish-package.json
```

The completion message includes title, description, 3-5 smart chapters,
duration, file size, production time, QC status, and exact paths.

## 6. Keep Improving Without Breaking Production

Record a correction:

```bash
python3 09_tools/vp.py observe \
  --summary "字幕整体偏快" \
  --category subtitle-rule \
  --priority P1
```

When production is idle:

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

The first daily TopK is locked at up to three items. Later observations stay in
the backlog. The stable production path remains available while candidates are
reviewed and tested.
