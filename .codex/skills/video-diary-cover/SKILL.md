---
name: video-diary-cover
description: Create, revise, route, and archive covers for Video Workshop. Use when the user asks for 封面, 样稿, 换封面, 字体更大, 黑边更细, cover gallery, or asks to make covers for 视频日记, 碎碎念, or 读书笔记/读书日记. Supports separate evolving cover routes and versions.
---

# Video Diary Cover

## Operating Model

Keep one Cover Skill and one CLI surface. Do not create a separate long-lived
Cover Agent or one Skill per visual style.

```text
Pencil design -> approved immutable style version -> deterministic daily make
              -> daily revisions + QC + gallery history
```

- Pencil is the low-frequency design environment for layout, hierarchy, color,
  type, and the matching `3:4` / `4:3` pair.
- The bundled renderer is the high-frequency production engine. Daily cover
  generation must not reopen Pencil when the approved version is unchanged.
- `references/cover-routes.json` stores public renderer tokens.
- `15_cover_gallery/designs/` stores ignored Pencil sources, previews, and
  version manifests.
- `15_cover_gallery/YYYY-MM-DD/` stores ignored daily revisions.

Official Pencil remains an external dependency. Never commit Pencil account
state, private assets, personal photos, or machine-specific paths.

## Required Reads

Read `references/cover-routes.md` before production. Read
`references/cover-routes.json` only when designing or debugging a style. Read
`15_cover_gallery/INDEX.md` only when local history is useful.

## Minimal CLI

The public workflow has three actions under one command group.

### 1. Design

Use Pencil MCP from a blank or existing `.pen` file, review both aspect ratios,
export the Pencil source and two preview images, then derive renderer tokens.
Register the approved version once:

```bash
npm run cover -- design \
  --route video-diary \
  --version v1.4.0 \
  --pencil-source 11_templates/pencil-cover-demos/video-diary-v1.4.0.pen \
  --preview-3x4 11_templates/pencil-cover-demos/video-diary-v1.4.0-3x4.png \
  --preview-4x3 11_templates/pencil-cover-demos/video-diary-v1.4.0-4x3.png \
  --tokens 11_templates/pencil-cover-demos/video-diary-v1.4.0-tokens.json \
  --activate \
  --note "Approved Pencil style"
```

For an existing renderer version, `--tokens` may be omitted. A registered
Pencil version is immutable; any visual or token change requires a new version.

### 2. Make

Generate, QC, lock, and archive the daily pair in one command:

```bash
npm run cover -- make \
  --date YYYY-MM-DD \
  --day-label "Day NN" \
  --portrait path/to/portrait.jpg \
  --landscape path/to/landscape.jpg \
  --title "TITLE" \
  --subtitle "SUBTITLE"
```

The route default version is used unless `--version` is explicit. The command
writes both exports, QC and pair manifest, updates `job.json`, archives both
daily revisions, and rebuilds the local gallery.

### 3. History

Inspect style versions and recent daily revisions:

```bash
npm run cover -- history --route video-diary --limit 20
```

Use `--json` on any action for Agent or ClipFlow-AI integration.

## Route Rules

- Default or `视频日记`: `video-diary`.
- `碎碎念`: `suisuinian` only when explicitly requested.
- `读书笔记` / `读书日记`: `reading-note` only when explicitly requested.
- Portrait photo is the `3:4` source; landscape photo is the `4:3` source.
- Do not crop a vertical frame into the horizontal cover when a landscape photo
  exists.

For `video-diary`, preserve the series label, date, Day metadata, main title,
and subtitle/description tag. A one-second title card uses the same approved
cover version.

## Production Flow

Cover and SRT work run in parallel. The Video Agent produces one cover pair
with one locked `route + styleVersion`, while the subtitle lane creates the
corrected external SRT. Both enter the same review pack. Final subtitle burn-in
and MP4 export wait for that confirmation.

## Compatibility

The existing `cover:render`, `cover:render-pair`, Pencil HTML export, archive,
and gallery scripts remain internal compatibility tools. Use them only for
debugging or fallback. Daily users and Agents should use `vp cover` through the
three actions above.

## Invariants

- Show samples before replacing a user-selected final cover.
- Never overwrite a registered style version.
- Never let daily title generation mutate design tokens.
- Fail when configured fonts, preview ratios, output dimensions, or title
  bounds are invalid.
- Keep every meaningful daily revision in the local gallery.
- Keep Pencil source assets local and ignored by Git.
