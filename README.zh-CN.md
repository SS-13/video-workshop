# Video Workshop

[English README](README.md)

一个本地优先的视频生产框架：把日常想法和真人口播，整理为经过校对
的字幕、成对封面、成片与发布包。

仓库只保存可复用的系统能力。想法、脚本、录制视频、导出成片、个人风格、
词库、运行日志和状态都保留在本地，默认不会提交到 Git。

## 能做什么

- 保存原始想法，生成提词器脚本；
- 入口和出口两次合规检视；
- 统一设计路线下的 `3:4`、`4:3` 双封面；
- 从真实音频转写，词级时间轴、词库纠错与时间轴检查；
- 封面和外挂 SRT 一次联合确认，再单次烧录；
- 生成发布标题、描述、智能章节、制作统计和发布包；
- 通过 Observation、TopK 和 Daily Engineering Loop 持续演进；
- 默认使用 v2 剪辑通道，同时保留 legacy 回退通道。

## 本地优先原则

```text
公共仓库：系统、规则、命令、测试、文档
本地工作区：你的内容、媒体、词库、风格、日志、状态
```

不要把原始口述、录像、导出视频、Cookie、账号状态或个人资料提交到公共仓库。

## 环境要求

| 依赖 | 最低要求 | 用途 |
| --- | --- | --- |
| Git | 当前受支持版本 | 克隆、更新、回滚 |
| Python | 3.10+ | 控制面、封面和字幕工具 |
| Node.js + npm | Node 20+ | 项目命令和 JavaScript 工具 |
| FFmpeg + FFprobe | 含 `ass`、`subtitles`、`drawtext` | 音频、字幕和渲染 |
| Pillow | `requirements.txt` 指定版本 | 封面渲染 |
| 中文字体 | 一种可读中文字体 | 中文封面和字幕 |
| 本地语音识别 | whisper.cpp 或 OpenAI Whisper | 真实音频转写 |

推荐使用 `whisper.cpp + ggml-base.bin`。OpenAI Whisper 可作为回退。

macOS 的常见安装方式：

```bash
brew install git python node ffmpeg whisper-cpp
```

安装推荐模型：

```bash
mkdir -p "$HOME/.cache/whisper.cpp"
curl -L \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin \
  -o "$HOME/.cache/whisper.cpp/ggml-base.bin"
```

## 初始化一个新副本

```bash
git clone https://github.com/SS-13/video-workshop.git
cd video-workshop
python3 -m pip install -r requirements.txt
npm run edit:deps
npm run setup
npm run doctor
npm run context
```

`npm run setup` 会创建所有被 Git 忽略、但运行系统所需的本地目录和种子文件，
不会覆盖已有内容。不要手动补建目录。

在开始前，AI Agent 应与用户确认：

1. 默认内容类型，默认是 `video-diary`；
2. 发布平台和封面比例，当前内置默认是抖音 `3:4`、`4:3`；
3. 视频日记 Day 起始编号；
4. 是否允许基于本地历史内容生成个人风格与字幕词库。

当前 `npm run doctor` 通过后，应至少满足：

```text
valid=true
ready_for_content=true
ready_for_render=true
loop_ready=true
```

## 第一次制作

### 1. 创建当天内容空间

```bash
npm run new-day -- YYYY-MM-DD

# 导入既有系列时指定 Day
npm run new-day -- YYYY-MM-DD --day 42
```

所有内容采用日期优先的键：

```text
YYYY-MM-DD/<content-type>/<sequence>
```

默认视频日记为：

```text
YYYY-MM-DD/video-diary/001
```

同一天同一类型的第二条内容使用 `002`。

### 2. 输入想法与录制

原始想法保留在：

```text
01_inbox/YYYY-MM-DD/video-diary/001.md
```

AI 在完成入口检视后生成提词器脚本：

```text
02_scripts/YYYY-MM-DD/video-diary/001.md
```

将原始录像放入：

```text
03_recordings/YYYY-MM-DD/video-diary/001/
```

脚本只是录制参考。字幕文本和时间轴始终以真实口播为准。

### 3. 先确认封面和字幕

录制上传后，默认 v2 路线会并行完成：

```text
封面双图 + 真实音频转写 + 词级时间轴 + SRT 纠错 + 自动 QC
```

命令：

```bash
npm run edit:render-day-v2 -- --date YYYY-MM-DD --model base --stop-after-review
```

系统会生成联合确认包。确认封面、外挂 SRT 和插入计划后，再执行一次最终烧录：

```bash
npm run edit:render-day-v2 -- --date YYYY-MM-DD --from-stage review --confirmed
```

遇到 v2 回归时，可立即使用 legacy：

```bash
npm run edit:render-day-legacy -- --date YYYY-MM-DD --mode standard
```

## 日常生产规则

```text
想法 -> 合规 -> 脚本 -> 录制
     -> 封面线路 + 字幕线路
     -> 联合确认 -> 合规 -> 单次渲染
     -> 发布包 -> 统计 -> 演进记录
```

- 最多两行字幕；
- 字幕文字和时间轴以真实音频为准；
- 默认无 BGM；
- 不覆盖或移动原始录像；
- 图片插入必须先确认时间、位置与尺寸；
- 日常视频优先内容、字幕准确性和安全区，不优先复杂动效；
- 成片后会生成标题、描述、智能章节、制作结果与 Tag。

## 封面系统

封面采用双层工作方式：

```text
Pencil：低频设计、建立并冻结风格版本
Renderer：高频日常生产、生成双比例封面
```

日常只需要三类动作：

```bash
# 登记已确认的 Pencil 设计版本
npm run cover -- design --help

# 生成、质检、归档当天双封面
npm run cover -- make --help

# 查看风格版本和最近修订
npm run cover -- history --route video-diary
```

Pencil 源文件和个人预览图保留在本地封面画廊；日常使用批准后的 renderer
tokens，不应每天重新打开 Pencil。

## 系统演进与版本

所有工作流修正先记录为 Observation：

```bash
python3 09_tools/vp.py observe \
  --summary "字幕整体偏快" \
  --category subtitle-rule \
  --priority P1
```

在没有视频生产锁时运行每日演进：

```bash
python3 09_tools/vp.py evolve --date YYYY-MM-DD
```

TopK 事项有验证证据后，写入追加式完成清单：

```bash
python3 09_tools/vp.py evolve complete CAND-xxxxxxxxxxxx \
  --date YYYY-MM-DD \
  --change-type feature \
  --evidence path/to/test-report.md
```

启用 GitHub Issues 集成后，每晚在 Loop 结束后同步公开安全的 TopK：

```bash
python3 09_tools/vp.py evolve issues sync \
  --date YYYY-MM-DD \
  --if-enabled
```

每个 TopK 都会映射到一个 Issue，标题直接使用事项摘要，不添加 `TopK` 前缀。
Issue 使用 `type:bug / type:feature / type:other` 分类，并且只保留一个动态
优先级标签。比如原始 `P3` 事项每过一天依次更新为 `P2`、`P1`、`P0`，不会
重复开单。`vp evolve complete` 验证后，Issue 变为 `status:verified`；关联 PR
使用 `Closes #N`，只有合并到 `main` 后才由 GitHub 自动关闭。

- 每日默认只锁定 TopK=3；
- 新需求持续进入 Backlog，不打断当天已锁定的 TopK；
- 完成事项应带测试、产物或验收证据；
- 完成项不会返回 Candidate，并保持 `releaseTarget=null`，直到进入明确的 Release 计划；
- 后续 Release 按 `bugfix`、`feature`、`major-evolution` 分类组织；
- Canary、回退与人工确认仍是版本切换的必要门禁。
- 非公开范围也会建立 Issue，但只显示 Candidate ID、类型和动态优先级；个人语料、
  内容 ID、证据路径和原始生产问题始终保留在本地。

完成态的 CLI、Schema、测试和默认规则属于公开框架；真实完成清单、验收证据和
个人产物仍保留在被 Git 忽略的本地工作区。

## 主要文档

- [AGENTS.md](AGENTS.md)：AI Agent 的操作规则与数据边界
- [START_HERE.md](START_HERE.md)：新副本和首条视频路径
- [PIPELINE.md](PIPELINE.md)：系统和产物地图
- [WORKFLOW.md](WORKFLOW.md)：当前生产工作流
- [.codex/agents/README.md](.codex/agents/README.md)：Agent 所有权
- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献范围、测试和隐私规则

## 隐私与提交前检查

默认 `.gitignore` 会忽略想法、脚本、媒体、导出成片、个人词库、风格、日志、
运行状态、封面画廊和凭据。每次公开推送前仍应检查暂存区：

```bash
git diff --cached --name-only
git diff --cached --check
```

不要提交绝对路径、账号 Cookie、视频文件或个人口述。

## 许可证

[MIT](LICENSE)
