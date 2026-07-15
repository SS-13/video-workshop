import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MONTH_RE = /^\d{4}-\d{2}$/;
const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".MP4", ".MOV", ".M4V"]);
const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]);
const LARGE_FILE_BYTES = 20 * 1024 * 1024;
const BIG_INTERMEDIATE_BYTES = 100 * 1024 * 1024;

const STAGE_DIRS = [
  ["01_inbox", "原始想法"],
  ["02_scripts", "提词器脚本"],
  ["03_recordings", "原始视频"],
  ["04_videos", "剪辑工程"],
  ["05_exports", "发布包"],
  ["06_logs", "日志台账"],
  ["15_cover_gallery", "封面陈列"],
  ["16_monthly_archive", "月度归档"]
];

const EDIT_NOTE_NAMES = [
  "BRIEF.md",
  "EDIT_DECISIONS.md",
  "STORYBOARD.md",
  "REPORT.md"
];

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const dateArg = args.find((arg) => DATE_RE.test(arg));
  const outArg = args.find((arg) => arg.startsWith("--out="));
  const date = dateArg ?? formatDate(new Date());

  return {
    date,
    outputPath: outArg?.split("=")[1] ?? null
  };
};

const formatDate = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const pathExists = async (filePath) => {
  try {
    await stat(filePath);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") {
      return false;
    }

    throw error;
  }
};

const readText = async (filePath) => {
  try {
    return await readFile(filePath, "utf-8");
  } catch (error) {
    if (error.code === "ENOENT") {
      return "";
    }

    throw error;
  }
};

const formatBytes = (bytes) => {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
};

const formatTokenCount = (tokens) => {
  if (!tokens) {
    return "-";
  }

  if (tokens >= 1000) {
    return `${Math.round(tokens / 1000)}k tokens`;
  }

  return `${tokens} tokens`;
};

const walkFiles = async (dirPath) => {
  if (!await pathExists(dirPath)) {
    return [];
  }

  const entries = await readdir(dirPath, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(dirPath, entry.name);

    if (entry.isDirectory()) {
      files.push(...await walkFiles(entryPath));
      continue;
    }

    if (entry.isFile()) {
      const fileStat = await stat(entryPath);
      files.push({
        path: entryPath,
        bytes: fileStat.size,
        extension: path.extname(entryPath)
      });
    }
  }

  return files;
};

const getDirSummary = async (root, dirName) => {
  const dirPath = path.join(root, dirName);
  const files = await walkFiles(dirPath);
  const bytes = files.reduce((sum, file) => sum + file.bytes, 0);
  return {
    dirName,
    fileCount: files.length,
    bytes
  };
};

const splitCsvLine = (line) => {
  const cells = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const nextChar = line[index + 1];

    if (char === "\"" && inQuotes && nextChar === "\"") {
      cell += "\"";
      index += 1;
      continue;
    }

    if (char === "\"") {
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

const readLedger = async (root) => {
  const ledgerPath = path.join(root, "06_logs", "publish-ledger.csv");
  const content = await readText(ledgerPath);
  const lines = content.split(/\r?\n/).filter((line) => line.trim());

  if (lines.length < 2) {
    return [];
  }

  const headers = splitCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = splitCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]));
  });
};

const listDateDirs = async (root, dirName) => {
  const dirPath = path.join(root, dirName);
  if (!await pathExists(dirPath)) {
    return [];
  }

  const entries = await readdir(dirPath, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => DATE_RE.test(name))
    .sort();
};

const listDateFiles = async (root, dirName) => {
  return listDateDirs(root, dirName);
};

const getDates = async (root, ledgerRows) => {
  const dates = new Set(ledgerRows.map((row) => row.date).filter((date) => DATE_RE.test(date)));

  for (const date of await listDateFiles(root, "01_inbox")) {
    dates.add(date);
  }

  for (const date of await listDateFiles(root, "02_scripts")) {
    dates.add(date);
  }

  for (const dirName of ["03_recordings", "04_videos", "05_exports", "15_cover_gallery"]) {
    for (const date of await listDateDirs(root, dirName)) {
      dates.add(date);
    }
  }

  return [...dates].sort();
};

const listFilesShallow = async (dirPath) => {
  if (!await pathExists(dirPath)) {
    return [];
  }

  const entries = await readdir(dirPath, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    if (!entry.isFile()) {
      continue;
    }

    const filePath = path.join(dirPath, entry.name);
    const fileStat = await stat(filePath);
    files.push({
      name: entry.name,
      path: filePath,
      bytes: fileStat.size,
      extension: path.extname(entry.name)
    });
  }

  return files;
};

const safeJson = async (filePath) => {
  const content = await readText(filePath);
  if (!content.trim()) {
    return null;
  }

  try {
    return JSON.parse(content);
  } catch {
    return null;
  }
};

const summarizeDate = async (root, date, ledgerRow) => {
  const contentPath = [date, "video-diary", "001"];
  const inboxPath = path.join(root, "01_inbox", date, "video-diary", "001.md");
  const scriptPath = path.join(root, "02_scripts", date, "video-diary", "001.md");
  const logPath = path.join(root, "06_logs", date, "video-diary", "001.md");
  const recordingDir = path.join(root, "03_recordings", ...contentPath);
  const videoDir = path.join(root, "04_videos", ...contentPath);
  const exportDir = path.join(root, "05_exports", ...contentPath);
  const coverDir = path.join(root, "15_cover_gallery", ...contentPath);
  const recordingFiles = await listFilesShallow(recordingDir);
  const exportFiles = await listFilesShallow(exportDir);
  const coverFiles = await listFilesShallow(coverDir);
  const preprocessedManifest = await safeJson(path.join(videoDir, "preprocessed", "preprocess_manifest.json"));
  const finalVideos = exportFiles.filter((file) => /_Day\d+_video-diary\.mp4$/i.test(file.name));
  const finalCovers = exportFiles.filter((file) => /_Day\d+_cover\.jpe?g$/i.test(file.name));
  const nonStandardExports = exportFiles.filter((file) => {
    if (!VIDEO_EXTENSIONS.has(file.extension) && !IMAGE_EXTENSIONS.has(file.extension)) {
      return false;
    }

    return !/_Day\d+_(video-diary|cover)\.(mp4|jpe?g)$/i.test(file.name);
  });
  const missingEditNotes = [];

  if (await pathExists(videoDir)) {
    for (const noteName of EDIT_NOTE_NAMES) {
      if (!await pathExists(path.join(videoDir, noteName))) {
        missingEditNotes.push(noteName);
      }
    }
  }

  return {
    date,
    dayLabel: ledgerRow?.day_label ?? "",
    topic: ledgerRow?.topic ?? "",
    status: ledgerRow?.status ?? "",
    videoDuration: ledgerRow?.video_duration ?? "",
    estimatedTokens: ledgerRow?.estimated_tokens ?? "",
    notes: ledgerRow?.notes ?? "",
    hasInbox: await pathExists(inboxPath),
    hasScript: await pathExists(scriptPath),
    hasLog: await pathExists(logPath),
    hasVideoDir: await pathExists(videoDir),
    recordingCount: recordingFiles.filter((file) => VIDEO_EXTENSIONS.has(file.extension)).length,
    finalVideoCount: finalVideos.length,
    finalCoverCount: finalCovers.length,
    coverVersionCount: coverFiles.filter((file) => /^v\d+_/.test(file.name)).length,
    nonStandardExports,
    missingEditNotes,
    preprocessProcessedCount: preprocessedManifest?.processedCount ?? null,
    preprocessTrimmedCount: preprocessedManifest?.trimmedCount ?? null
  };
};

const parseEstimatedTokenNumber = (value) => {
  const text = String(value ?? "");
  const match = text.match(/([0-9.]+)\s*k/i);
  if (match) {
    return Math.round(Number(match[1]) * 1000);
  }

  const numberMatch = text.match(/[0-9]+/);
  return numberMatch ? Number(numberMatch[0]) : null;
};

const summarizeTokens = (ledgerRows) => {
  const rows = ledgerRows
    .map((row) => ({
      date: row.date,
      dayLabel: row.day_label,
      topic: row.topic,
      estimatedTokens: row.estimated_tokens,
      tokenNumber: parseEstimatedTokenNumber(row.estimated_tokens),
      notes: row.notes
    }))
    .filter((row) => row.tokenNumber);
  const total = rows.reduce((sum, row) => sum + row.tokenNumber, 0);
  const dailyRows = rows.filter((row) => !String(row.notes).includes("搭建成本"));
  const dailyTotal = dailyRows.reduce((sum, row) => sum + row.tokenNumber, 0);
  const dailyAverage = dailyRows.length ? Math.round(dailyTotal / dailyRows.length) : 0;
  const maxRow = rows.length ? rows.reduce((max, row) => (
    row.tokenNumber > max.tokenNumber ? row : max
  ), rows[0]) : null;

  return {
    rows,
    total,
    dailyAverage,
    maxRow
  };
};

const readWorkerStatus = async (root) => {
  const pidPath = path.join(root, "06_logs", "feishu-worker.pid");
  const statusPath = path.join(root, "06_logs", "feishu-worker-status.json");
  const pidText = (await readText(pidPath)).trim();
  const pid = Number(pidText);
  const status = await safeJson(statusPath);
  let running = false;

  if (Number.isInteger(pid) && pid > 0) {
    try {
      process.kill(pid, 0);
      running = true;
    } catch {
      running = false;
    }
  }

  return {
    pid: Number.isInteger(pid) && pid > 0 ? pid : null,
    running,
    status
  };
};

const findLooseExports = async (root) => {
  const exportRoot = path.join(root, "05_exports");
  const files = await listFilesShallow(exportRoot);
  return files.filter((file) => VIDEO_EXTENSIONS.has(file.extension) || IMAGE_EXTENSIONS.has(file.extension));
};

const findDsStoreFiles = async (root) => {
  const files = await walkFiles(root);
  return files.filter((file) => path.basename(file.path) === ".DS_Store");
};

const findLargeFiles = async (root) => {
  const files = [];

  for (const dirName of ["03_recordings", "04_videos", "05_exports", "15_cover_gallery"]) {
    const dirPath = path.join(root, dirName);
    const dirFiles = await walkFiles(dirPath);
    files.push(...dirFiles.filter((file) => file.bytes >= LARGE_FILE_BYTES));
  }

  return files.sort((a, b) => b.bytes - a.bytes);
};

const findBigIntermediates = async (root) => {
  const files = await walkFiles(path.join(root, "04_videos"));
  return files
    .filter((file) => file.bytes >= BIG_INTERMEDIATE_BYTES)
    .filter((file) => VIDEO_EXTENSIONS.has(file.extension))
    .sort((a, b) => b.bytes - a.bytes);
};

const findMonthlyArchiveState = async (root) => {
  const archiveRoot = path.join(root, "16_monthly_archive");
  if (!await pathExists(archiveRoot)) {
    return [];
  }

  const entries = await readdir(archiveRoot, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => MONTH_RE.test(name))
    .sort();
};

const relative = (root, filePath) => path.relative(root, filePath);

const yesNo = (value) => value ? "是" : "否";

const buildReport = async (root, auditDate) => {
  const ledgerRows = await readLedger(root);
  const dates = await getDates(root, ledgerRows);
  const ledgerByDate = new Map(ledgerRows.map((row) => [row.date, row]));
  const dateSummaries = [];

  for (const date of dates) {
    dateSummaries.push(await summarizeDate(root, date, ledgerByDate.get(date)));
  }

  const dirSummaries = [];
  for (const [dirName, label] of STAGE_DIRS) {
    const summary = await getDirSummary(root, dirName);
    dirSummaries.push({ ...summary, label });
  }

  const tokenSummary = summarizeTokens(ledgerRows);
  const looseExports = await findLooseExports(root);
  const dsStoreFiles = await findDsStoreFiles(root);
  const largeFiles = await findLargeFiles(root);
  const bigIntermediates = await findBigIntermediates(root);
  const worker = await readWorkerStatus(root);
  const monthlyArchives = await findMonthlyArchiveState(root);
  const totalStorage = dirSummaries.reduce((sum, item) => sum + item.bytes, 0);
  const nonStandardExportCount = dateSummaries.reduce(
    (sum, item) => sum + item.nonStandardExports.length,
    0
  );
  const missingEditNotes = dateSummaries
    .filter((item) => item.hasVideoDir && item.missingEditNotes.length)
    .map((item) => `${item.date}: ${item.missingEditNotes.join(", ")}`);
  const publishDataGaps = ledgerRows.filter((row) => (
    !row.published_at ||
    !row.manual_minutes ||
    !row.total_elapsed ||
    !row.douyin_url
  ));

  const lines = [
    `# ${auditDate} 视频日记工作流自检报告`,
    "",
    "## 结论",
    "",
    `- 已形成稳定主线：想法 -> 脚本 -> 录制 -> 封面/字幕确认 -> 导出 -> 发布包 -> 日志。`,
    `- 当前最大成本不是文本，而是视频工程文件和字幕渲染：项目内可见产物约 ${formatBytes(totalStorage)}。`,
    `- 已记录 token 估算合计约 ${formatTokenCount(tokenSummary.total)}；剔除明确标注为搭建成本的记录后，日常均值约 ${formatTokenCount(tokenSummary.dailyAverage)}。`,
    `- 发布台账存在 ${publishDataGaps.length} 条字段不完整记录；工程记录缺口 ${missingEditNotes.length} 条。`,
    "",
    "## 阶段容量",
    "",
    "| 阶段 | 目录 | 文件数 | 大小 | 判断 |",
    "| --- | --- | ---: | ---: | --- |",
    ...dirSummaries.map((item) => {
      const judgement = item.dirName === "03_recordings" || item.dirName === "04_videos" || item.dirName === "05_exports"
        ? "大文件主来源"
        : "轻量";
      return `| ${item.label} | \`${item.dirName}/\` | ${item.fileCount} | ${formatBytes(item.bytes)} | ${judgement} |`;
    }),
    "",
    "## 每日状态",
    "",
    "| 日期 | Day | 主题 | 录制数 | 成片 | 封面 | 封面版本 | token估算 | 备注 |",
    "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ...dateSummaries.map((item) => [
      item.date,
      item.dayLabel || "-",
      item.topic || "-",
      item.recordingCount,
      item.finalVideoCount,
      item.finalCoverCount,
      item.coverVersionCount,
      item.estimatedTokens || "-",
      item.notes || "-"
    ].map((cell) => String(cell).replace(/\|/g, "/")).join(" | ")).map((row) => `| ${row} |`),
    "",
    "## 漏洞",
    "",
    `1. 发布台账字段缺口：${publishDataGaps.length} 条记录缺少发布时间、链接或实际耗时。`,
    `2. 工程记录缺口：${missingEditNotes.length} 个日期缺少预期的工程记录。`,
    `3. 飞书 worker 状态：${worker.status || "unknown"}；远程录入前应先检查状态。`,
    `4. 非标准导出：日期发布目录中存在 ${nonStandardExportCount} 个中间媒体文件。`,
    `5. 大型中间文件：共有 ${bigIntermediates.length} 个文件超过 ${formatBytes(BIG_INTERMEDIATE_BYTES)}。`,
    "",
    "## 冗余",
    "",
    `- \`05_exports/\` 根目录还有 ${looseExports.length} 个未进入日期目录的散落导出文件。`,
    `- 日期发布目录里有 ${nonStandardExportCount} 个非标准导出媒体文件，主要是早期转写版/增强版等中间版本。`,
    `- \`04_videos/\` 里有 ${bigIntermediates.length} 个超过 ${formatBytes(BIG_INTERMEDIATE_BYTES)} 的中间视频，它们方便返工，但月末应进入人工清理清单。`,
    `- macOS 自动生成的 \`.DS_Store\` 有 ${dsStoreFiles.length} 个，小但会让目录清单显得乱。`,
    `- \`16_monthly_archive/\` 已存在 ${monthlyArchives.join(", ") || "无"}，当前还没到月末，里面可能只是阶段性快照，不应被当作最终归档。`,
    "",
    "## 大文件 Top 12",
    "",
    "| 大小 | 路径 |",
    "| ---: | --- |",
    ...largeFiles.slice(0, 12).map((file) => `| ${formatBytes(file.bytes)} | \`${relative(root, file.path)}\` |`),
    "",
    "## Token 观察",
    "",
    "| 日期 | Day | 主题 | 估算 token | 主要原因 |",
    "| --- | --- | --- | ---: | --- |",
    ...tokenSummary.rows.map((row) => `| ${row.date} | ${row.dayLabel} | ${row.topic} | ${row.estimatedTokens} | ${row.notes || "-"} |`),
    "",
    "判断：",
    "",
    "- 明确标注为搭建成本的记录不进入日常均值。",
    `- 当前最高单条记录：${tokenSummary.maxRow ? `${tokenSummary.maxRow.date} / ${tokenSummary.maxRow.dayLabel} / ${tokenSummary.maxRow.estimatedTokens}` : "无"}。`,
    "- 日常生产和系统改造应分开计量，避免把一次性开发成本误判为成片成本。",
    "",
    "## 已落地优化",
    "",
    "- 新增 `npm run audit-workflow -- YYYY-MM-DD`，以后可以一键生成本报告。",
    "- 自检命令只读文件，不渲染、不上传、不删除，适合每周或每 3 条视频跑一次。",
    "",
    "## 建议优先级",
    "",
    "1. 优先补齐发布台账中的发布时间、链接和实际耗时。",
    "2. 对非标准导出和大型中间文件生成清单，由用户逐项决定是否删除。",
    "3. 把可复用问题记录为 Observation，在生产空闲时运行 Daily Engineering Loop。",
    "4. 发布后补台账：只要你发完抖音，回一句发布时间/链接/实际手动时间，就能让趋势分析真正可用。",
    "5. 月末只运行 `npm run archive-month -- YYYY-MM` 生成清单，不自动删除；大文件必须人工逐个确认。",
    "",
    "## 待人工确认",
    "",
    ...[
      looseExports.length ? `- 早期散落导出是否保留：${looseExports.map((file) => `\`${relative(root, file.path)}\``).join("、")}` : null,
      missingEditNotes.length ? `- 是否要求每天强制补齐工程记录：${missingEditNotes.join("；")}` : null,
      publishDataGaps.length ? `- 是否补录发布时间/链接/手动耗时：${publishDataGaps.map((row) => row.date).join("、")}` : null,
      worker.status?.status === "crashed" ? "- 飞书 worker 是否需要今天出门前重启并观察一轮。" : null
    ].filter(Boolean),
    ""
  ];

  return lines.join("\n");
};

const main = async () => {
  const { date, outputPath } = parseArgs(process.argv);
  const root = process.cwd();
  const target = outputPath
    ? path.resolve(root, outputPath)
    : path.join(root, "06_logs", `workflow-audit-${date}.md`);
  const report = await buildReport(root, date);

  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, report, "utf-8");

  console.log(`audit=${path.relative(root, target)}`);
};

await main();
