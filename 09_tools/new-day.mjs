import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const requestedStartDay = Number(process.env.VIDEO_DIARY_START_DAY ?? "1");
const FIRST_DAY_NUMBER = Number.isInteger(requestedStartDay) && requestedStartDay > 0
  ? requestedStartDay
  : 1;
const LAST_PREPROJECT_DAY_NUMBER = FIRST_DAY_NUMBER - 1;
const DAY_LABEL_RE = /(?:^|[^A-Za-z0-9])Day\s*(\d+)(?=$|[^A-Za-z0-9])/i;
const CONTENT_LEDGER_HEADERS = [
  "content_id",
  "date",
  "column",
  "day_label",
  "title",
  "status",
  "inbox_ref",
  "script_ref",
  "recording_ref",
  "workspace_ref",
  "export_ref",
  "cover_ref",
  "published_at",
  "douyin_url",
  "notes"
];

const getToday = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
};

const parseDayNumber = (value) => {
  const match = String(value ?? "").match(DAY_LABEL_RE);
  return match ? Number(match[1]) : null;
};

const splitCsvLine = (line) => {
  const cells = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const nextChar = line[index + 1];

    if (char === '"' && inQuotes && nextChar === '"') {
      cell += '"';
      index += 1;
      continue;
    }

    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }

    if (char === "," && !inQuotes) {
      cells.push(cell);
      cell = "";
      continue;
    }

    cell += char;
  }

  cells.push(cell);
  return cells;
};

const readPublishLedgerDayEntries = async (root) => {
  const ledgerPath = path.join(root, "06_logs", "publish-ledger.csv");
  let content = "";

  try {
    content = await readFile(ledgerPath, "utf-8");
  } catch (error) {
    if (error.code === "ENOENT") {
      return [];
    }

    throw error;
  }

  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) {
    return [];
  }

  const headers = splitCsvLine(lines[0]);
  const dateIndex = headers.indexOf("date");
  const dayLabelIndex = headers.indexOf("day_label");

  if (dateIndex < 0 || dayLabelIndex < 0) {
    return [];
  }

  return lines.slice(1).flatMap((line) => {
    const cells = splitCsvLine(line);
    const dayNumber = parseDayNumber(cells[dayLabelIndex]);

    if (!DATE_RE.test(cells[dateIndex] ?? "") || !dayNumber) {
      return [];
    }

    return [{
      date: cells[dateIndex],
      dayNumber,
      source: "publish-ledger"
    }];
  });
};

const readExportDayEntries = async (root) => {
  const exportRoot = path.join(root, "05_exports");
  let dateDirs = [];

  try {
    dateDirs = await readdir(exportRoot, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") {
      return [];
    }

    throw error;
  }

  const entries = [];

  for (const dateDir of dateDirs) {
    if (!dateDir.isDirectory() || !DATE_RE.test(dateDir.name)) {
      continue;
    }

    const dateDirPath = path.join(exportRoot, dateDir.name);
    let files = [];

    try {
      files = await readdir(dateDirPath, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const file of files) {
      if (!file.isFile()) {
        continue;
      }

      const dayNumber = parseDayNumber(file.name);
      if (!dayNumber) {
        continue;
      }

      entries.push({
        date: dateDir.name,
        dayNumber,
        source: "exports"
      });
    }
  }

  return entries;
};

const getKnownDayEntries = async (root) => [
  ...await readPublishLedgerDayEntries(root),
  ...await readExportDayEntries(root)
];

const getDayNumber = async (root, date) => {
  const entries = await getKnownDayEntries(root);
  const sameDateDays = entries
    .filter((entry) => entry.date === date)
    .map((entry) => entry.dayNumber);

  if (sameDateDays.length > 0) {
    return Math.max(...sameDateDays);
  }

  const knownDays = entries.map((entry) => entry.dayNumber);
  const maxKnownDay = Math.max(LAST_PREPROJECT_DAY_NUMBER, ...knownDays);
  return maxKnownDay + 1;
};

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const date = args.find((arg) => DATE_RE.test(arg)) ?? getToday();
  const dayArg = args.find((arg) => arg.startsWith("--day="));
  const dayFlagIndex = args.indexOf("--day");
  const dayValue = dayArg?.split("=")[1] ?? (
    dayFlagIndex >= 0 ? args[dayFlagIndex + 1] : undefined
  );
  const explicitDayNumber = dayValue ? Number(dayValue) : null;

  if (explicitDayNumber !== null && (
    !Number.isInteger(explicitDayNumber) ||
    explicitDayNumber < 1
  )) {
    throw new Error("Day number must be a positive integer.");
  }

  return { date, explicitDayNumber };
};

const writeIfAbsent = async (filePath, content) => {
  try {
    await writeFile(filePath, content, { flag: "wx" });
    return "created";
  } catch (error) {
    if (error.code === "EEXIST") {
      return "exists";
    }

    throw error;
  }
};

const writeJsonAtomic = async (filePath, payload) => {
  const temporaryPath = `${filePath}.tmp-${process.pid}`;
  await writeFile(temporaryPath, `${JSON.stringify(payload, null, 2)}\n`, "utf-8");
  await rename(temporaryPath, filePath);
};

const csvCell = (value) => {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const updateContentLedger = async (root, date, dayNumber, dayLabel) => {
  const stateDir = path.join(root, "00_state");
  const ledgerPath = path.join(stateDir, "content-ledger.csv");
  const contentId = `${date}_Day${dayNumber}`;
  await mkdir(stateDir, { recursive: true });

  let content = `${CONTENT_LEDGER_HEADERS.join(",")}\n`;
  try {
    content = await readFile(ledgerPath, "utf-8");
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }

  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  if (lines.slice(1).some((line) => splitCsvLine(line)[0] === contentId)) {
    return "exists";
  }

  const row = [
    contentId,
    date,
    "video-diary",
    dayLabel,
    "",
    "initialized",
    `01_inbox/${date}.md`,
    `02_scripts/${date}.md`,
    `03_recordings/${date}/`,
    `04_videos/${date}/`,
    "",
    "",
    "",
    "",
    "Initialized by new-day."
  ].map(csvCell).join(",");
  const normalized = `${content.trimEnd()}\n${row}\n`;
  const temporaryPath = `${ledgerPath}.tmp-${process.pid}`;
  await writeFile(temporaryPath, normalized, "utf-8");
  await rename(temporaryPath, ledgerPath);
  return "created";
};

const updateDayCounter = async (root, date, dayNumber) => {
  const stateDir = path.join(root, "00_state");
  const counterPath = path.join(stateDir, "day-counter.json");
  await mkdir(stateDir, { recursive: true });

  let current = {};
  try {
    current = JSON.parse(await readFile(counterPath, "utf-8"));
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }

  const currentDay = Number(current.lastDay ?? 0);
  if (currentDay > dayNumber) {
    return "newer-state-kept";
  }

  await writeJsonAtomic(counterPath, {
    ...current,
    series: "video-diary",
    lastDay: dayNumber,
    lastContentId: `${date}_Day${dayNumber}`,
    updatedAt: date,
    rules: {
      videoDiaryIncrementsDay: true,
      suisuinianIncrementsDay: false,
      readingNoteIncrementsDay: false
    },
    notes: "Only the video-diary column increments Day. Updated by new-day."
  });
  return currentDay === dayNumber ? "unchanged" : "updated";
};

const buildInbox = (date) => `# ${date} 灵感收集

## 话题 1
- 内容类型：问题解法 / 想法分享
- 时间：
- 原始口述：

- 这条在回答什么问题：
- 谁会遇到这个问题 / 谁会对这个想法感兴趣：
- 我这条想给出的最小结论：
- 录制状态：未生成脚本

## 话题 2
- 内容类型：问题解法 / 想法分享
- 时间：
- 原始口述：

- 这条在回答什么问题：
- 谁会遇到这个问题 / 谁会对这个想法感兴趣：
- 我这条想给出的最小结论：
- 录制状态：未生成脚本

## 话题 3
- 内容类型：问题解法 / 想法分享
- 时间：
- 原始口述：

- 这条在回答什么问题：
- 谁会遇到这个问题 / 谁会对这个想法感兴趣：
- 我这条想给出的最小结论：
- 录制状态：未生成脚本
`;

const buildScript = (date, dayNumber, dayLabel) => `# ${date} 视频日记脚本

## 基本信息

- 日期：${date}
- 视频编号：${dayLabel}
- 成片方向：横屏 16:9 / 竖屏 9:16
- 今日总主题：
- 预计总时长：5-10分钟
- 今日主类型：问题解法 / 想法分享 / 混合

## 开场

\`\`\`text
今天是${date}。
这是我的第${dayNumber}条视频日记。
今天想记录一个问题 / 一个想法。
\`\`\`

## S01 话题一

- 内容类型：问题解法 / 想法分享
### 一句话核心

### 这条在回答什么问题


### 谁会对这条内容有感觉


### 提词器文案

\`\`\`text

\`\`\`

### 结构提示

- 问题解法型：问题 -> 卡点 -> 解法 -> 动作
- 想法分享型：经历/观察 -> 我现在的理解 -> 为什么想先记下来

### 拍摄提示

- 预计时长：1-2分钟
- 情绪：自然，像和未来的自己说话
- 必须说到：
- 结尾金句：
- 前2秒句子：

## S02 话题二

- 内容类型：问题解法 / 想法分享
### 一句话核心

### 这条在回答什么问题


### 谁会对这条内容有感觉


### 提词器文案

\`\`\`text

\`\`\`

### 结构提示

- 问题解法型：问题 -> 卡点 -> 解法 -> 动作
- 想法分享型：经历/观察 -> 我现在的理解 -> 为什么想先记下来

### 拍摄提示

- 预计时长：1-2分钟
- 情绪：自然，像和未来的自己说话
- 必须说到：
- 结尾金句：
- 前2秒句子：

## S03 话题三

- 内容类型：问题解法 / 想法分享
### 一句话核心

### 这条在回答什么问题


### 谁会对这条内容有感觉


### 提词器文案

\`\`\`text

\`\`\`

### 结构提示

- 问题解法型：问题 -> 卡点 -> 解法 -> 动作
- 想法分享型：经历/观察 -> 我现在的理解 -> 为什么想先记下来

### 拍摄提示

- 预计时长：1-2分钟
- 情绪：自然，像和未来的自己说话
- 必须说到：
- 结尾金句：
- 前2秒句子：

## 自动剪辑要求

- 原始视频目录：\`03_recordings/${date}/\`
- 输出工程目录：\`04_videos/${date}/\`
- 最终发布包：\`05_exports/${date}/\`
- 每段前加标题卡：是
- 字幕：自动生成 / 先留占位
- BGM：无 / 轻微
- 剪映后处理：只做最后微调
`;

const buildLog = (date, dayLabel) => `# ${date} 视频日记运行日志

## 结果

- 状态：
- 视频编号：${dayLabel}
- 最终视频：
- 视频时长：
- 抖音状态：
- 抖音链接：
- 是否进入剪映：
- 当天是否有输出：
- 是否达成 5-10 分钟目标：

## 时间记录

- 想法记录：
- 脚本整理：
- 手机录制：
- 素材导入：
- 自动剪辑：
- 剪映微调：
- 总耗时：

## Agent 记录

- Idea Agent：
- Script Agent：
- Video Pipeline Agent：
- Log Agent：

## Token / 成本记录

- 用户报告 token：
- Codex 可见 token：
- 估算 token：
- 估算成本：
- 备注：

## 发布记录

- 发布时间：
- 发布平台：抖音
- 发布链接：
- 发布标题：
- 发布封面版本：
- 发布台账：\`00_state/publish-ledger.csv\`（兼容镜像：\`06_logs/publish-ledger.csv\`）

## 可持续性判断

- 今天是否完成输出：
- 总耗时是否可持续：
- 最大耗时环节：
- 是否需要优化流程：

## 问题

-

## 下次改进

-
`;

const main = async () => {
  const { date, explicitDayNumber } = parseArgs(process.argv);
  const root = process.cwd();
  const dayNumber = explicitDayNumber ?? await getDayNumber(root, date);
  const dayLabel = `Day ${dayNumber}`;
  const dirs = [
    "01_inbox",
    "02_scripts",
    "03_recordings",
    "04_videos",
    "05_exports",
    "06_logs",
    "15_cover_gallery",
    path.join("03_recordings", date),
    path.join("04_videos", date),
    path.join("05_exports", date),
    path.join("15_cover_gallery", date)
  ];

  for (const dir of dirs) {
    await mkdir(path.join(root, dir), { recursive: true });
  }

  const files = [
    {
      path: path.join(root, "01_inbox", `${date}.md`),
      content: buildInbox(date)
    },
    {
      path: path.join(root, "02_scripts", `${date}.md`),
      content: buildScript(date, dayNumber, dayLabel)
    },
    {
      path: path.join(root, "06_logs", `${date}.md`),
      content: buildLog(date, dayLabel)
    }
  ];

  const results = [];

  for (const file of files) {
    const status = await writeIfAbsent(file.path, file.content);
    results.push({ filePath: file.path, status });
  }

  const counterStatus = await updateDayCounter(root, date, dayNumber);
  const ledgerStatus = await updateContentLedger(root, date, dayNumber, dayLabel);

  console.log(`Ready for ${date} (${dayLabel})`);
  for (const result of results) {
    console.log(`- ${result.status}: ${path.relative(root, result.filePath)}`);
  }
  console.log(`- ready: 03_recordings/${date}/`);
  console.log(`- ready: 04_videos/${date}/`);
  console.log(`- ready: 05_exports/${date}/`);
  console.log(`- ready: 06_logs/${date}.md`);
  console.log(`- ready: 15_cover_gallery/${date}/`);
  console.log(`- day-counter: ${counterStatus} -> ${dayLabel}`);
  console.log(`- content-ledger: ${ledgerStatus} -> ${date}_Day${dayNumber}`);
  console.log("");
  console.log("Next:");
  console.log(`1. Write 02_scripts/${date}.md`);
  console.log(`2. Put phone videos into 03_recordings/${date}/`);
  console.log(`3. Ask Codex: 今天要处理的视频日记日期是：${date}，按 WORKFLOW.md 跑自动粗剪。`);
};

await main();
