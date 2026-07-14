---
name: video-diary-script
description: Rewrite raw video diary ideas into teleprompter scripts for Video Workshop. Use when the user says 生成脚本, 编写脚本, 改写成口播, or asks to turn 01_inbox content into 02_scripts. Preserve the user's plain personal speaking style.
---

# Video Diary Script

## Core Rule

Turn raw thought into speakable teleprompter copy. Do not make it a marketing script, essay, motivational speech, or generic short-video hook.

## Required Reads

Read these before rewriting:

```text
01_inbox/YYYY-MM-DD.md
02_scripts/YYYY-MM-DD.md
00_system/defaults/speaking-style.md
.codex/skills/video-diary-script/references/retention/two-second-retention.md
```

If `10_skills/personal-speaking-style/SKILL.md` exists, read it after the public
default and treat it as the higher-priority local override. On a first clone,
follow `.codex/skills/video-production-bootstrap/references/personalization.md`
when the user asks the AI to learn from historical content. If the user adds a
newer language-habit file or asks to switch versions, that explicit file wins.

Use `references/retention/two-second-retention.md` as the opening-quality gate. Apply it lightly: improve the first two seconds without making the script sound like a generic influencer hook.

If `12_research/high-frequency-questions.md` exists, use it as a light reference
only. It can help identify what recurring problem the raw idea belongs to, but
it must not override today's actual thought.

## Style

- Keep the user's concrete facts and original thinking order.
- Prefer short, speakable sentences.
- Keep natural phrases like `其实`, `我现在想的是`, `今天先记录到这里` when useful.
- Remove repeated filler only when it blocks口播.
- Do not invent grand conclusions.
- Do not add empty hot-take framing.
- Prefer the user's pattern: concrete event -> current observation -> temporary understanding -> short close.
- Make the first sentence concrete enough for a stranger to understand why this topic matters in 2 seconds.
- Do not change `01_inbox/`.

## Content Type Routing

Before writing the script, classify the topic from `01_inbox`:

- `问题解法`: the raw idea answers a concrete recurring problem.
- `想法分享`: the raw idea records an observation, judgment, feeling, or personal change.

If the type is unclear, default to `想法分享` for video diary.

For `问题解法`, use this structure:

```text
问题 -> 场景/卡点 -> 我的理解或解法 -> 可以先做的动作
```

For `想法分享`, use this structure:

```text
经历/观察 -> 我现在的理解 -> 为什么今天想先记下来
```

Do not force every diary into a utilitarian problem-solving script. The workflow keeps both lines.

## Column Rules

- If the user does not explicitly name `碎碎念` or `读书笔记`, treat the script as `视频日记`.
- `视频日记`: default to one main topic per day. Merge only when the user explicitly says there are multiple topics for the same video.
- `碎碎念`: no strict topic limit. It may wander and follow the user's spoken thought flow.
- `读书笔记`: organize around the book/chapter/reading observation, but keep the user's own reading response as the center.
- For all columns, keep script generation separate from editing; do not start剪辑 after writing the script.

## Output Structure

Update `02_scripts/YYYY-MM-DD.md` with:

```text
## S01 标题

### 内容类型

### 一句话核心

### 这条在回答什么问题

### 谁会对这条内容有感觉

### 提词器文案

text block with speakable copy

### 拍摄提示

### 前2秒检查
```

For one-topic days, remove unused `S02/S03` placeholder sections if they distract from execution.

In `### 前2秒检查`, include:

- 首句
- 首帧/首屏建议
- 可能降低两秒跳出率的原因

## State Update

After generating a script, update the corresponding topic in `01_inbox/YYYY-MM-DD.md`:

```text
- 录制状态：已生成脚本
```

Update `06_logs/YYYY-MM-DD.md` Script Agent line with a short factual note.

When manually creating a new script day instead of running `npm run new-day -- YYYY-MM-DD`, also create the matching workflow directories:

```text
03_recordings/YYYY-MM-DD/
04_videos/YYYY-MM-DD/
05_exports/YYYY-MM-DD/
15_cover_gallery/YYYY-MM-DD/
```

## Stop Condition

Stop after script generation. Do not start video editing unless the user explicitly says the video has been uploaded and asks to start剪辑.
