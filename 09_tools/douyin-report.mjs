import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const ROOT = process.cwd();
const LOG_DIR = path.join(ROOT, "06_logs");
const VIDEOS_CSV = path.join(LOG_DIR, "douyin-videos.csv");
const SNAPSHOTS_CSV = path.join(LOG_DIR, "douyin-metrics-snapshots.csv");
const PUBLISH_LEDGER_CSV = path.join(LOG_DIR, "publish-ledger.csv");
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const formatDate = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const dateArg = args.find((arg) => DATE_RE.test(arg));
  const outArg = args.find((arg) => arg.startsWith("--out="));
  const date = dateArg ?? formatDate(new Date());

  return {
    date,
    outputPath: outArg?.split("=").slice(1).join("=") ?? path.join(LOG_DIR, `douyin-report-${date}.md`)
  };
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

const readCsv = async (filePath) => {
  const content = await readText(filePath);
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

const normalizeText = (value) => String(value ?? "")
  .toLowerCase()
  .replace(/#[^\s#]+/g, "")
  .replace(/[^\p{L}\p{N}]+/gu, "");

const toNumber = (value) => {
  const text = String(value ?? "").trim();
  if (!text || text === "-") {
    return null;
  }

  const multiplier = text.includes("万") ? 10000 : 1;
  const match = text.replaceAll(",", "").match(/\d+(?:\.\d+)?/);
  return match ? Math.round(Number(match[0]) * multiplier) : null;
};

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }

  return String(value);
};

const formatDelta = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }

  if (value > 0) {
    return `+${value}`;
  }

  return String(value);
};

const extractPublishTime = (rawNote) => {
  const match = String(rawNote ?? "").match(/(\d{4})年(\d{2})月(\d{2})日\s+(\d{2}):(\d{2})/);
  if (!match) {
    return "";
  }

  return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}`;
};

const extractTitle = (rawNote) => {
  const note = String(rawNote ?? "").trim();
  const match = note.match(/^(?:\d{2}:\d{2}\s+)?(.+?)\s+编辑作品/);
  return match?.[1]?.trim() ?? "";
};

const videoKey = (row) => {
  const id = row.douyin_item_id || row.douyin_video_id || row.douyin_url;
  if (id) {
    return `id:${id}`;
  }

  return `meta:${row.publish_time}|${normalizeText(row.title)}`;
};

const snapshotKey = (row) => {
  const id = row.douyin_item_id || row.douyin_video_id || row.douyin_url;
  if (id) {
    return `id:${id}`;
  }

  const publishTime = extractPublishTime(row.raw_note);
  const title = extractTitle(row.raw_note);
  return `meta:${publishTime}|${normalizeText(title)}`;
};

const getSnapshotDate = (row) => String(row.snapshot_at ?? "").slice(0, 10);

const startOfWeek = (dateText) => {
  const date = new Date(`${dateText}T00:00:00`);
  const day = date.getDay() || 7;
  date.setDate(date.getDate() - day + 1);
  return formatDate(date);
};

const endOfWeek = (dateText) => {
  const date = new Date(`${startOfWeek(dateText)}T00:00:00`);
  date.setDate(date.getDate() + 6);
  return formatDate(date);
};

const enrichVideoRows = (videoRows, ledgerRows) => {
  const ledgerByDate = new Map(ledgerRows.map((row) => [row.date, row]));

  return videoRows.map((row) => {
    const ledger = row.matched_date ? ledgerByDate.get(row.matched_date) : null;
    return {
      ...row,
      day_label: row.day_label || ledger?.day_label || "-",
      topic: row.topic || ledger?.topic || "-",
      published_at: ledger?.published_at || row.publish_time || "-"
    };
  });
};

const groupSnapshots = (snapshotRows) => {
  const groups = new Map();

  for (const row of snapshotRows) {
    const key = snapshotKey(row);
    if (!groups.has(key)) {
      groups.set(key, []);
    }

    groups.get(key).push({
      ...row,
      viewsNumber: toNumber(row.views),
      likesNumber: toNumber(row.likes),
      commentsNumber: toNumber(row.comments),
      favoritesNumber: toNumber(row.favorites),
      sharesNumber: toNumber(row.shares)
    });
  }

  for (const rows of groups.values()) {
    rows.sort((left, right) => String(left.snapshot_at).localeCompare(String(right.snapshot_at)));
  }

  return groups;
};

const getLatestOnOrBefore = (rows, date) => rows
  .filter((row) => getSnapshotDate(row) <= date)
  .at(-1) ?? null;

const getPreviousBefore = (rows, snapshotAt) => {
  const index = rows.findIndex((row) => row.snapshot_at === snapshotAt);
  return index > 0 ? rows[index - 1] : null;
};

const getFirstWithin = (rows, startDate, endDate) => rows
  .find((row) => {
    const snapshotDate = getSnapshotDate(row);
    return snapshotDate >= startDate && snapshotDate <= endDate;
  }) ?? null;

const getLatestWithin = (rows, startDate, endDate) => rows
  .filter((row) => {
    const snapshotDate = getSnapshotDate(row);
    return snapshotDate >= startDate && snapshotDate <= endDate;
  })
  .at(-1) ?? null;

const truncate = (value, length = 26) => {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length)}...` : text;
};

const buildDailyRows = (videos, snapshotGroups, date) => videos
  .map((video) => {
    const snapshots = snapshotGroups.get(videoKey(video)) ?? [];
    const latest = getLatestOnOrBefore(snapshots, date);
    if (!latest) {
      return null;
    }

    const previous = getPreviousBefore(snapshots, latest.snapshot_at);
    return {
      day: video.day_label || "-",
      title: video.title || "-",
      publishTime: video.publish_time || video.published_at || "-",
      views: latest.viewsNumber,
      viewDelta: previous && latest.viewsNumber !== null && previous.viewsNumber !== null
        ? latest.viewsNumber - previous.viewsNumber
        : null,
      likes: latest.likesNumber,
      comments: latest.commentsNumber,
      favorites: latest.favoritesNumber,
      shares: latest.sharesNumber,
      averageWatchTime: latest.average_watch_time || "-",
      coverClickRate: latest.cover_click_rate || "-"
    };
  })
  .filter(Boolean)
  .sort((left, right) => String(right.publishTime).localeCompare(String(left.publishTime)));

const buildWeeklyRows = (videos, snapshotGroups, startDate, endDate) => videos
  .map((video) => {
    const snapshots = snapshotGroups.get(videoKey(video)) ?? [];
    const first = getFirstWithin(snapshots, startDate, endDate);
    const latest = getLatestWithin(snapshots, startDate, endDate);
    if (!latest) {
      return null;
    }

    return {
      day: video.day_label || "-",
      title: video.title || "-",
      publishTime: video.publish_time || video.published_at || "-",
      views: latest.viewsNumber,
      weekDelta: first && latest.viewsNumber !== null && first.viewsNumber !== null
        ? latest.viewsNumber - first.viewsNumber
        : null,
      interactions: [
        latest.likesNumber,
        latest.commentsNumber,
        latest.favoritesNumber,
        latest.sharesNumber
      ].reduce((sum, value) => sum + (value ?? 0), 0),
      averageWatchTime: latest.average_watch_time || "-"
    };
  })
  .filter(Boolean)
  .sort((left, right) => (right.weekDelta ?? -1) - (left.weekDelta ?? -1));

const table = (headers, rows) => [
  `| ${headers.join(" | ")} |`,
  `| ${headers.map(() => "---").join(" | ")} |`,
  ...rows
].join("\n");

const renderDailyTable = (rows) => table(
  ["Day", "标题", "发布时间", "播放", "较上次", "赞", "评", "藏", "转", "平均播放", "封面点击"],
  rows.map((row) => `| ${row.day} | ${truncate(row.title)} | ${row.publishTime} | ${formatNumber(row.views)} | ${formatDelta(row.viewDelta)} | ${formatNumber(row.likes)} | ${formatNumber(row.comments)} | ${formatNumber(row.favorites)} | ${formatNumber(row.shares)} | ${row.averageWatchTime} | ${row.coverClickRate} |`)
);

const renderWeeklyTable = (rows) => table(
  ["Day", "标题", "发布时间", "当前播放", "本周新增", "互动合计", "平均播放"],
  rows.map((row) => `| ${row.day} | ${truncate(row.title)} | ${row.publishTime} | ${formatNumber(row.views)} | ${formatDelta(row.weekDelta)} | ${formatNumber(row.interactions)} | ${row.averageWatchTime} |`)
);

const summarize = (dailyRows, weeklyRows) => {
  const publishedRows = dailyRows.filter((row) => row.day !== "-");
  const bestViews = [...dailyRows].sort((left, right) => (right.views ?? 0) - (left.views ?? 0))[0];
  const bestGrowth = [...dailyRows].sort((left, right) => (right.viewDelta ?? -1) - (left.viewDelta ?? -1))[0];
  const bestWeek = [...weeklyRows].sort((left, right) => (right.weekDelta ?? -1) - (left.weekDelta ?? -1))[0];

  return [
    `- 已匹配视频日记：${publishedRows.length} 条`,
    `- 当前最高播放：${bestViews ? `${bestViews.day} ${formatNumber(bestViews.views)}` : "-"}`,
    `- 最近一次播放变化最大：${bestGrowth ? `${bestGrowth.day} ${formatDelta(bestGrowth.viewDelta)}` : "-"}`,
    `- 本周新增播放最大：${bestWeek ? `${bestWeek.day} ${formatDelta(bestWeek.weekDelta)}` : "-"}`
  ].join("\n");
};

const renderReport = ({ date, weekStart, weekEnd, dailyRows, weeklyRows }) => `# ${date} 抖音视频日记数据简报

## 概览

${summarize(dailyRows, weeklyRows)}

## 日简报

${dailyRows.length ? renderDailyTable(dailyRows) : "- 暂无轮询快照。"}

## 周简报

统计范围：${weekStart} 至 ${weekEnd}

${weeklyRows.length ? renderWeeklyTable(weeklyRows) : "- 暂无本周轮询快照。"}

## 说明

- 播放变化基于 06_logs/douyin-metrics-snapshots.csv 的相邻快照计算。
- 当前抖音页面未暴露公开视频 ID 时，使用“发布时间 + 标题”匹配到 Day。
- 本报告只用于个人视频日记复盘，不执行发布、编辑或删除操作。
`;

const main = async () => {
  const args = parseArgs(process.argv);
  const [videoRows, snapshotRows, ledgerRows] = await Promise.all([
    readCsv(VIDEOS_CSV),
    readCsv(SNAPSHOTS_CSV),
    readCsv(PUBLISH_LEDGER_CSV)
  ]);

  const videos = enrichVideoRows(videoRows, ledgerRows);
  const snapshotGroups = groupSnapshots(snapshotRows);
  const weekStart = startOfWeek(args.date);
  const weekEnd = endOfWeek(args.date);
  const dailyRows = buildDailyRows(videos, snapshotGroups, args.date);
  const weeklyRows = buildWeeklyRows(videos, snapshotGroups, weekStart, weekEnd);
  const report = renderReport({
    date: args.date,
    weekStart,
    weekEnd,
    dailyRows,
    weeklyRows
  });

  await mkdir(path.dirname(args.outputPath), { recursive: true });
  await writeFile(args.outputPath, report, "utf-8");
  console.log(`report=${path.relative(ROOT, args.outputPath)}`);
  console.log(`daily_rows=${dailyRows.length}`);
  console.log(`weekly_rows=${weeklyRows.length}`);
};

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
