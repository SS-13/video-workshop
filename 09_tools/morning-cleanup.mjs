import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MEDIA_EXTENSIONS = new Set([
  ".mp4",
  ".mov",
  ".m4v",
  ".mkv",
  ".webm",
  ".png",
  ".jpg",
  ".jpeg",
  ".MP4",
  ".MOV",
  ".M4V",
  ".PNG",
  ".JPG",
  ".JPEG"
]);

const VIDEO_EXTENSIONS = new Set([
  ".mp4",
  ".mov",
  ".m4v",
  ".mkv",
  ".webm",
  ".MP4",
  ".MOV",
  ".M4V"
]);
const DEFAULT_MIN_BYTES = 20 * 1024 * 1024;

const SCAN_ROOTS = [
  "03_recordings",
  "04_videos",
  "05_exports"
];

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const date = args.find((arg) => DATE_RE.test(arg)) ?? formatDate(new Date());
  const outArg = args.find((arg) => arg.startsWith("--out="));
  const minBytesArg = args.find((arg) => arg.startsWith("--min-mb="));
  const listAll = args.includes("--all");
  const minMb = minBytesArg ? Number(minBytesArg.split("=")[1]) : null;

  return {
    date,
    outputPath: outArg?.split("=")[1] ?? null,
    minBytes: listAll ? 0 : (
      Number.isFinite(minMb) && minMb >= 0 ? minMb * 1024 * 1024 : DEFAULT_MIN_BYTES
    )
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
    return new Map();
  }

  const headers = splitCsvLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const cells = splitCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]));
  });

  return new Map(rows.map((row) => [row.date, row]));
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

const extractDateFromPath = (root, filePath) => {
  const relativePath = path.relative(root, filePath);
  const segments = relativePath.split(path.sep);
  const segmentDate = segments.find((segment) => DATE_RE.test(segment));

  if (segmentDate) {
    return segmentDate;
  }

  const filenameMatch = path.basename(filePath).match(/\d{4}-\d{2}-\d{2}/);
  return filenameMatch ? filenameMatch[0] : null;
};

const classifyStage = (relativePath) => {
  if (relativePath.startsWith("03_recordings/")) {
    return "原始视频";
  }

  if (relativePath.startsWith("04_videos/")) {
    return "剪辑工程媒体";
  }

  if (relativePath.startsWith("05_exports/")) {
    return "发布包媒体";
  }

  return "其他媒体";
};

const getPublishWarning = (ledgerRow) => {
  if (!ledgerRow) {
    return "无台账记录，清理前确认";
  }

  if (ledgerRow.status !== "已发布" || !ledgerRow.published_at || !ledgerRow.douyin_url) {
    return "未完整记录发布信息，清理前确认";
  }

  return "已发布可考虑清理";
};

const listCleanupCandidates = async (root, cutoffDate, minBytes) => {
  const files = [];

  for (const scanRoot of SCAN_ROOTS) {
    const scanRootPath = path.join(root, scanRoot);
    const allFiles = await walkFiles(scanRootPath);
    files.push(...allFiles);
  }

  return files
    .filter((file) => MEDIA_EXTENSIONS.has(file.extension))
    .map((file) => ({
      ...file,
      date: extractDateFromPath(root, file.path),
      relativePath: path.relative(root, file.path),
      stage: classifyStage(path.relative(root, file.path)),
      isVideo: VIDEO_EXTENSIONS.has(file.extension)
    }))
    .filter((file) => file.date && file.date < cutoffDate)
    .filter((file) => file.bytes >= minBytes)
    .sort((a, b) => {
      if (a.date !== b.date) {
        return a.date.localeCompare(b.date);
      }

      return b.bytes - a.bytes;
    });
};

const summarizeBy = (items, getKey) => {
  const summary = new Map();

  for (const item of items) {
    const key = getKey(item);
    const current = summary.get(key) ?? { count: 0, bytes: 0 };
    current.count += 1;
    current.bytes += item.bytes;
    summary.set(key, current);
  }

  return [...summary.entries()].sort(([a], [b]) => a.localeCompare(b));
};

const buildReport = async (root, cutoffDate, minBytes) => {
  const ledgerByDate = await readLedger(root);
  const candidates = await listCleanupCandidates(root, cutoffDate, minBytes);
  const totalBytes = candidates.reduce((sum, file) => sum + file.bytes, 0);
  const videoBytes = candidates
    .filter((file) => file.isVideo)
    .reduce((sum, file) => sum + file.bytes, 0);
  const byDate = summarizeBy(candidates, (file) => file.date);
  const byStage = summarizeBy(candidates, (file) => file.stage);

  const lines = [
    `# ${cutoffDate} 早晨视频文件清理清单`,
    "",
    "## 规则",
    "",
    "- 只检查今天之前的媒体文件。",
    "- 长期保留文本知识库：`01_inbox/`、`02_scripts/`、`06_logs/`、剪辑文字记录、封面索引和发布台账。",
    "- 只把视频、字幕图片、发布包封面等媒体文件列入候选。",
    "- 本命令只生成清单，不删除任何文件。",
    "- 如果发布台账没有完整记录发布时间和抖音链接，清理前需要人工确认。",
    "",
    "## 总览",
    "",
    `- 截止日期：${cutoffDate}`,
    `- 列表阈值：${minBytes === 0 ? "全部媒体文件" : `${formatBytes(minBytes)} 以上`}`,
    `- 候选文件：${candidates.length} 个`,
    `- 候选总大小：${formatBytes(totalBytes)}`,
    `- 其中视频文件大小：${formatBytes(videoBytes)}`,
    "",
    "## 按日期",
    "",
    "| 日期 | 文件数 | 大小 | 发布状态 | 判断 |",
    "| --- | ---: | ---: | --- | --- |",
    ...byDate.map(([date, summary]) => {
      const row = ledgerByDate.get(date);
      return `| ${date} | ${summary.count} | ${formatBytes(summary.bytes)} | ${row?.status || "无记录"} | ${getPublishWarning(row)} |`;
    }),
    "",
    "## 按阶段",
    "",
    "| 阶段 | 文件数 | 大小 |",
    "| --- | ---: | ---: |",
    ...byStage.map(([stage, summary]) => `| ${stage} | ${summary.count} | ${formatBytes(summary.bytes)} |`),
    "",
    "## 候选文件",
    "",
    "| 日期 | 阶段 | 大小 | 路径 | 判断 |",
    "| --- | --- | ---: | --- | --- |",
    ...candidates.map((file) => {
      const row = ledgerByDate.get(file.date);
      return `| ${file.date} | ${file.stage} | ${formatBytes(file.bytes)} | \`${file.relativePath}\` | ${getPublishWarning(row)} |`;
    }),
    "",
    "## 手动清理原则",
    "",
    "- 不要删除 `01_inbox/` 和 `02_scripts/`。",
    "- 不要批量删除目录。",
    "- 如果要清理，只能按这份清单逐个确认明确文件路径。",
    "- 优先清理 `04_videos/**/intermediate/`、`04_videos/**/preprocessed/`、旧的 `05_exports/**/*.mp4`。",
    "- 当天目录不进入清理候选，方便当天返工。",
    ""
  ];

  return {
    report: lines.join("\n"),
    candidateCount: candidates.length,
    totalBytes
  };
};

const main = async () => {
  const { date, outputPath, minBytes } = parseArgs(process.argv);
  const root = process.cwd();
  const target = outputPath
    ? path.resolve(root, outputPath)
    : path.join(root, "06_logs", `morning-cleanup-${date}.md`);
  const { report, candidateCount, totalBytes } = await buildReport(root, date, minBytes);

  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, report, "utf-8");

  console.log(`cleanup_report=${path.relative(root, target)}`);
  console.log(`candidate_files=${candidateCount}`);
  console.log(`candidate_size=${formatBytes(totalBytes)}`);
  console.log("No files were deleted.");
};

await main();
