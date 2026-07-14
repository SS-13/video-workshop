import { mkdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";

const ROOT = process.cwd();
const LOG_DIR = path.join(ROOT, "06_logs");
const RUNTIME_DIR = path.join(ROOT, ".runtime", "douyin-browser-profile");
const RAW_DIR = path.join(LOG_DIR, "douyin-raw");
const VIDEOS_CSV = path.join(LOG_DIR, "douyin-videos.csv");
const SNAPSHOTS_CSV = path.join(LOG_DIR, "douyin-metrics-snapshots.csv");
const PUBLISH_LEDGER_CSV = path.join(LOG_DIR, "publish-ledger.csv");
const DEFAULT_CHROME_PATH = process.platform === "darwin"
  ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  : process.platform === "win32"
    ? "C:/Program Files/Google/Chrome/Application/chrome.exe"
    : "google-chrome";
const CHROME_PATH = process.env.CHROME_BIN || DEFAULT_CHROME_PATH;
const DEFAULT_PORT = 9223;
const DEFAULT_URL = "https://creator.douyin.com/creator-micro/content/manage";
const VIDEO_HEADERS = [
  "douyin_item_id",
  "douyin_video_id",
  "douyin_url",
  "publish_time",
  "title",
  "matched_date",
  "day_label",
  "topic",
  "source",
  "first_seen_at",
  "last_seen_at"
];
const SNAPSHOT_HEADERS = [
  "snapshot_at",
  "douyin_item_id",
  "douyin_video_id",
  "douyin_url",
  "views",
  "likes",
  "comments",
  "favorites",
  "shares",
  "average_watch_time",
  "cover_click_rate",
  "followers",
  "source",
  "raw_note"
];

const sleep = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
});

const formatDate = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const isoNow = () => new Date().toISOString();

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const command = args[0] && !args[0].startsWith("--") ? args[0] : "poll";
  const getValue = (name, fallback = null) => {
    const inline = args.find((arg) => arg.startsWith(`--${name}=`));
    if (inline) {
      return inline.split("=").slice(1).join("=");
    }

    const index = args.indexOf(`--${name}`);
    return index >= 0 ? args[index + 1] : fallback;
  };

  return {
    command,
    url: getValue("url", DEFAULT_URL),
    date: getValue("date", formatDate(new Date())),
    port: Number(getValue("port", DEFAULT_PORT)),
    keepOpen: args.includes("--keep-open"),
    waitMs: Number(getValue("wait-ms", 8000)),
    help: args.includes("--help") || args.includes("-h")
  };
};

const printHelp = () => {
  console.log(`Douyin browser polling

Usage:
  npm run douyin:login
  npm run douyin:poll -- --url URL
  node 09_tools/douyin-poll.mjs poll --date YYYY-MM-DD --keep-open

Commands:
  login   Open a dedicated Chrome profile for Douyin login.
  poll    Read visible Douyin creator/public page data and write local CSV snapshots.

Options:
  --url URL       Page to open. Defaults to creator content management.
  --date DATE    Report date. Defaults to today.
  --port PORT    Chrome remote debugging port. Defaults to 9223.
  --keep-open    Keep Chrome open after polling.
  --wait-ms MS   Wait after navigation before extraction. Defaults to 8000.
`);
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

const ensureCsv = async (filePath, headers) => {
  await mkdir(path.dirname(filePath), { recursive: true });
  const content = await readText(filePath);
  if (!content.trim()) {
    await writeFile(filePath, `${headers.join(",")}\n`, "utf-8");
  }
};

const csvEscape = (value) => {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) {
    return `"${text.replaceAll("\"", "\"\"")}"`;
  }

  return text;
};

const parseCsvLine = (line) => {
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

const readCsv = async (filePath, headers) => {
  await ensureCsv(filePath, headers);
  const content = await readText(filePath);
  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length <= 1) {
    return [];
  }

  const actualHeaders = parseCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return Object.fromEntries(actualHeaders.map((header, index) => [header, cells[index] ?? ""]));
  });
};

const readCsvWithHeaders = async (filePath) => {
  const content = await readText(filePath);
  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length) {
    return { headers: [], rows: [] };
  }

  const headers = parseCsvLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]));
  });

  return { headers, rows };
};

const writeCsv = async (filePath, headers, rows) => {
  const lines = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(","))
  ];
  await writeFile(filePath, `${lines.join("\n")}\n`, "utf-8");
};

const appendCsvRows = async (filePath, headers, rows) => {
  const existing = await readCsv(filePath, headers);
  await writeCsv(filePath, headers, [...existing, ...rows]);
};

const normalizeText = (value) => String(value ?? "")
  .toLowerCase()
  .replace(/#[^\s#]+/g, "")
  .replace(/[^\p{L}\p{N}]+/gu, "");

const dateFromPublishTime = (value) => {
  const match = String(value ?? "").match(/\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : "";
};

const appendNote = (note, next) => {
  if (!next) {
    return note ?? "";
  }

  if (String(note ?? "").includes(next)) {
    return note ?? "";
  }

  return [note, next].filter(Boolean).join("/");
};

const findLedgerMatch = (video, ledgerRows) => {
  const publishDate = dateFromPublishTime(video.publish_time);
  if (!publishDate) {
    return null;
  }

  const sameDateRows = ledgerRows.filter((row) => row.date === publishDate);
  if (sameDateRows.length === 1) {
    return sameDateRows[0];
  }

  const titleNorm = normalizeText(video.title);
  return sameDateRows.find((row) => {
    const topicNorm = normalizeText(row.topic);
    if (!topicNorm) {
      return false;
    }

    return titleNorm.includes(topicNorm) || topicNorm.includes(titleNorm);
  }) ?? null;
};

const matchVideosToLedger = async () => {
  const videoRows = await readCsv(VIDEOS_CSV, VIDEO_HEADERS);
  const { headers: ledgerHeaders, rows: ledgerRows } = await readCsvWithHeaders(PUBLISH_LEDGER_CSV);
  if (!ledgerRows.length) {
    return { matched: 0 };
  }

  let matched = 0;
  for (const video of videoRows) {
    const ledgerRow = findLedgerMatch(video, ledgerRows);
    if (!ledgerRow) {
      continue;
    }

    matched += 1;
    video.matched_date = ledgerRow.date;
    video.day_label = ledgerRow.day_label;
    video.topic = ledgerRow.topic;

    if (ledgerRow.status === "待发布" || !ledgerRow.status) {
      ledgerRow.status = "已发布";
    }

    if (!ledgerRow.published_at) {
      ledgerRow.published_at = video.publish_time;
    }

    ledgerRow.notes = appendNote(ledgerRow.notes, "抖音轮询已匹配");
  }

  await writeCsv(VIDEOS_CSV, VIDEO_HEADERS, videoRows);
  await writeCsv(PUBLISH_LEDGER_CSV, ledgerHeaders, ledgerRows);
  return { matched };
};

const upsertVideos = async (videos, now) => {
  const rows = await readCsv(VIDEOS_CSV, VIDEO_HEADERS);
  const keyOf = (row) => row.douyin_item_id || row.douyin_video_id || row.douyin_url || `${row.title}|${row.publish_time}`;
  const byKey = new Map(rows.map((row) => [keyOf(row), row]));

  for (const video of videos) {
    const key = keyOf(video);
    if (!key.trim()) {
      continue;
    }

    const current = byKey.get(key);
    byKey.set(key, {
      douyin_item_id: video.douyin_item_id ?? current?.douyin_item_id ?? "",
      douyin_video_id: video.douyin_video_id ?? current?.douyin_video_id ?? "",
      douyin_url: video.douyin_url ?? current?.douyin_url ?? "",
      publish_time: video.publish_time ?? current?.publish_time ?? "",
      title: video.title ?? current?.title ?? "",
      matched_date: current?.matched_date ?? "",
      day_label: current?.day_label ?? "",
      topic: current?.topic ?? "",
      source: video.source ?? current?.source ?? "creator_browser",
      first_seen_at: current?.first_seen_at || now,
      last_seen_at: now
    });
  }

  await writeCsv(VIDEOS_CSV, VIDEO_HEADERS, [...byKey.values()]);
};

class CdpSession {
  constructor(wsUrl) {
    this.nextId = 1;
    this.pending = new Map();
    this.ws = new WebSocket(wsUrl);
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });

    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (!message.id || !this.pending.has(message.id)) {
        return;
      }

      const { resolve, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) {
        reject(new Error(message.error.message || "CDP command failed"));
        return;
      }

      resolve(message.result);
    });
  }

  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    const payload = JSON.stringify({ id, method, params });

    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(payload);
    });
  }

  close() {
    this.ws.close();
  }
}

const fetchJson = async (url) => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${url}`);
  }

  return response.json();
};

const waitForChrome = async (port) => {
  const deadline = Date.now() + 15000;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      return await fetchJson(`http://127.0.0.1:${port}/json/version`);
    } catch (error) {
      lastError = error;
      await sleep(500);
    }
  }

  throw lastError ?? new Error("Chrome did not become available.");
};

const launchChrome = async ({ port, url }) => {
  await mkdir(RUNTIME_DIR, { recursive: true });
  const child = spawn(CHROME_PATH, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${RUNTIME_DIR}`,
    "--no-first-run",
    "--no-default-browser-check",
    url
  ], {
    detached: true,
    stdio: "ignore"
  });

  child.unref();
  return child;
};

const getPageWebSocket = async (port, url) => {
  let pages = await fetchJson(`http://127.0.0.1:${port}/json/list`);
  let page = pages.find((item) => item.type === "page" && item.url.includes("douyin.com")) ??
    pages.find((item) => item.type === "page");

  if (!page) {
    await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {
      method: "PUT"
    }).catch(() => null);
    pages = await fetchJson(`http://127.0.0.1:${port}/json/list`);
    page = pages.find((item) => item.type === "page");
  }

  if (!page?.webSocketDebuggerUrl) {
    throw new Error("No controllable Chrome page found.");
  }

  return page.webSocketDebuggerUrl;
};

const evaluatePage = async (port, url, waitMs) => {
  const wsUrl = await getPageWebSocket(port, url);
  const cdp = new CdpSession(wsUrl);
  await cdp.open();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Page.navigate", { url });
  await sleep(waitMs);

  const expression = `(() => {
    const text = document.body ? document.body.innerText : "";
    const links = [...document.querySelectorAll("a")]
      .map((link) => ({
        text: (link.innerText || link.textContent || "").trim(),
        href: link.href || ""
      }))
      .filter((link) => link.text || link.href)
      .slice(0, 500);
    const cards = [...document.querySelectorAll("tr, li, [class*=card], [class*=item], [class*=video], [data-e2e]")]
      .map((node) => {
        const rect = node.getBoundingClientRect();
        return {
          tag: node.tagName,
          className: String(node.className || ""),
          text: (node.innerText || node.textContent || "").trim(),
          links: [...node.querySelectorAll("a")].map((link) => ({
            text: (link.innerText || link.textContent || "").trim(),
            href: link.href || ""
          })),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        };
      })
      .filter((node) => node.text && node.text.length >= 12)
      .slice(0, 800);
    const scripts = [...document.scripts]
      .map((script) => script.textContent || "")
      .filter((content) => /aweme|item_id|video_id|digg|comment|share|play|collect/.test(content))
      .map((content) => content.slice(0, 20000))
      .slice(0, 20);
    return {
      url: location.href,
      title: document.title,
      text,
      links,
      cards,
      scripts
    };
  })()`;

  const result = await cdp.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true
  });
  cdp.close();
  return result.result.value;
};

const parseMetricValue = (value) => {
  const text = String(value ?? "").replaceAll(",", "").trim();
  const match = text.match(/([0-9]+(?:\.[0-9]+)?)\s*([万wWkK]?)/);
  if (!match) {
    return "";
  }

  const number = Number(match[1]);
  const unit = match[2].toLowerCase();
  if (unit === "万" || unit === "w") {
    return String(Math.round(number * 10000));
  }
  if (unit === "k") {
    return String(Math.round(number * 1000));
  }

  return String(Math.round(number));
};

const extractMetric = (text, labels) => {
  for (const label of labels) {
    const patterns = [
      new RegExp(`${label}\\s*[:：]?\\s*([0-9][0-9.,]*(?:\\.[0-9]+)?\\s*[万wWkK]?)`),
      new RegExp(`([0-9][0-9.,]*(?:\\.[0-9]+)?\\s*[万wWkK]?)\\s*${label}`)
    ];

    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        return parseMetricValue(match[1]);
      }
    }
  }

  return "";
};

const extractDate = (text) => {
  const normalized = text
    .replaceAll("/", "-")
    .replaceAll(".", "-")
    .replace(/年/g, "-")
    .replace(/月/g, "-")
    .replace(/日/g, "");
  const fullDate = normalized.match(/\b20\d{2}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?\b/);
  if (fullDate) {
    return fullDate[0];
  }

  return "";
};

const extractIdFromUrl = (url) => {
  const text = String(url ?? "");
  const videoMatch = text.match(/video\/([0-9]+)/);
  if (videoMatch) {
    return videoMatch[1];
  }

  const modalMatch = text.match(/[?&]modal_id=([0-9]+)/);
  if (modalMatch) {
    return modalMatch[1];
  }

  return "";
};

const pickTitle = (text, linkText) => {
  const banned = /播放|点赞|评论|收藏|分享|转发|数据|删除|编辑|置顶|审核|公开|私密|发布时间/;
  const lines = String(text ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length >= 2 && line.length <= 80)
    .filter((line) => !banned.test(line))
    .filter((line) => !/^[0-9.,万wWkK\s:-]+$/.test(line));

  if (linkText && linkText.length >= 2 && linkText.length <= 80 && !banned.test(linkText)) {
    return linkText;
  }

  return lines[0] ?? "";
};

const extractVideos = (pageData, snapshotAt) => {
  const linear = extractVideosFromText(pageData.text, snapshotAt);
  if (linear.length > 0) {
    return linear;
  }

  const candidates = [];
  const seen = new Set();
  const candidateCards = pageData.cards
    .filter((card) => /播放|点赞|评论|收藏|分享|转发|浏览|获赞|数据|公开|作品/.test(card.text))
    .filter((card) => card.text.length <= 2000);

  for (const card of candidateCards) {
    const link = card.links.find((item) => /douyin\.com|video|modal_id/.test(item.href)) ?? card.links[0];
    const url = link?.href ?? "";
    const id = extractIdFromUrl(url);
    const title = pickTitle(card.text, link?.text);
    const views = extractMetric(card.text, ["播放", "浏览", "观看"]);
    const likes = extractMetric(card.text, ["点赞", "获赞"]);
    const comments = extractMetric(card.text, ["评论"]);
    const favorites = extractMetric(card.text, ["收藏"]);
    const shares = extractMetric(card.text, ["分享", "转发"]);
    const publishTime = extractDate(card.text);
    const hasMetric = views || likes || comments || favorites || shares;
    const key = id || url || `${title}|${publishTime}|${card.text.slice(0, 80)}`;

    if (!title || !hasMetric || seen.has(key)) {
      continue;
    }

    seen.add(key);
    candidates.push({
      video: {
        douyin_item_id: id,
        douyin_video_id: "",
        douyin_url: url,
        publish_time: publishTime,
        title,
        source: "creator_browser"
      },
      snapshot: {
        snapshot_at: snapshotAt,
        douyin_item_id: id,
        douyin_video_id: "",
        douyin_url: url,
        views,
        likes,
        comments,
        favorites,
      shares,
      average_watch_time: "",
      cover_click_rate: "",
      followers: "",
        source: "creator_browser",
        raw_note: card.text.replace(/\s+/g, " ").slice(0, 300)
      }
    });
  }

  return candidates;
};

const isDurationLine = (line) => /^\d{1,2}:\d{2}(?::\d{2})?$/.test(line);

const normalizePublishTime = (line) => extractDate(line);

const metricAfterLabel = (lines, startIndex, endIndex, label) => {
  const labelIndex = lines.findIndex((line, index) => (
    index >= startIndex && index < endIndex && line === label
  ));

  if (labelIndex < 0) {
    return "";
  }

  return parseMetricValue(lines[labelIndex + 1] ?? "");
};

const optionalMetricAfterLabel = (lines, startIndex, endIndex, label) => {
  const labelIndex = lines.findIndex((line, index) => (
    index >= startIndex && index < endIndex && line === label
  ));

  if (labelIndex < 0) {
    return "";
  }

  return String(lines[labelIndex + 1] ?? "").trim();
};

const extractVideosFromText = (text, snapshotAt) => {
  const lines = String(text ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const items = [];

  for (let index = 0; index < lines.length; index += 1) {
    if (!isDurationLine(lines[index])) {
      continue;
    }

    const title = lines[index + 1] ?? "";
    const publishIndex = lines.findIndex((line, nextIndex) => (
      nextIndex > index &&
      nextIndex < index + 20 &&
      /20\d{2}年\d{2}月\d{2}日\s+\d{2}:\d{2}/.test(line)
    ));

    if (!title || publishIndex < 0) {
      continue;
    }

    const nextDurationIndex = lines.findIndex((line, nextIndex) => (
      nextIndex > index && isDurationLine(line)
    ));
    const endIndex = nextDurationIndex > 0 ? nextDurationIndex : Math.min(lines.length, index + 45);
    const blockLines = lines.slice(index, endIndex);
    const block = blockLines.join(" ");
    const views = metricAfterLabel(lines, publishIndex, endIndex, "播放");
    const likes = metricAfterLabel(lines, publishIndex, endIndex, "点赞");
    const comments = metricAfterLabel(lines, publishIndex, endIndex, "评论");
    const shares = metricAfterLabel(lines, publishIndex, endIndex, "分享");
    const favorites = metricAfterLabel(lines, publishIndex, endIndex, "收藏");
    const averageWatchTime = optionalMetricAfterLabel(lines, publishIndex, endIndex, "平均播放时长");
    const coverClickRate = optionalMetricAfterLabel(lines, publishIndex, endIndex, "封面点击率");

    if (!views && !likes && !comments && !shares && !favorites) {
      continue;
    }

    items.push({
      video: {
        douyin_item_id: "",
        douyin_video_id: "",
        douyin_url: "",
        publish_time: normalizePublishTime(lines[publishIndex]),
        title,
        source: "creator_browser"
      },
      snapshot: {
        snapshot_at: snapshotAt,
        douyin_item_id: "",
        douyin_video_id: "",
        douyin_url: "",
        views,
        likes,
        comments,
        favorites,
        shares,
        average_watch_time: averageWatchTime,
        cover_click_rate: coverClickRate,
        followers: "",
        source: "creator_browser",
        raw_note: [
          block.slice(0, 220),
          averageWatchTime ? `avg_watch=${averageWatchTime}` : "",
          coverClickRate ? `cover_ctr=${coverClickRate}` : ""
        ].filter(Boolean).join(" | ")
      }
    });
  }

  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.video.title}|${item.video.publish_time}`;
    if (seen.has(key)) {
      return false;
    }

    seen.add(key);
    return true;
  });
};

const isLikelyLoginPage = (pageData) => {
  const text = `${pageData.title}\n${pageData.text}`;
  return /登录|扫码|验证码/.test(text) && !/作品管理|数据中心|播放|点赞/.test(text);
};

const writeRaw = async (date, pageData) => {
  await mkdir(RAW_DIR, { recursive: true });
  const target = path.join(RAW_DIR, `douyin-poll-${date}.json`);
  await writeFile(target, JSON.stringify(pageData, null, 2), "utf-8");
  return target;
};

const writeReport = async ({ date, pageData, rawPath, extracted, loginNeeded }) => {
  const target = path.join(LOG_DIR, `douyin-poll-${date}.md`);
  const lines = [
    `# ${date} 抖音数据轮询报告`,
    "",
    "## 结果",
    "",
    `- 页面标题：${pageData.title || ""}`,
    `- 页面 URL：${pageData.url || ""}`,
    `- 是否需要登录：${loginNeeded ? "是" : "否"}`,
    `- 识别作品数：${extracted.length}`,
    `- 原始页面快照：\`${path.relative(ROOT, rawPath)}\``,
    "",
    "## 识别作品",
    "",
    "| 标题 | 发布时间 | 播放 | 点赞 | 评论 | 收藏 | 分享 | 平均播放 | 封面点击 | 链接 |",
    "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ...extracted.map(({ video, snapshot }) => (
      `| ${video.title || "-"} | ${video.publish_time || "-"} | ${snapshot.views || "-"} | ${snapshot.likes || "-"} | ${snapshot.comments || "-"} | ${snapshot.favorites || "-"} | ${snapshot.shares || "-"} | ${snapshot.average_watch_time || "-"} | ${snapshot.cover_click_rate || "-"} | ${video.douyin_url || "-"} |`
    )),
    "",
    "## 判断",
    "",
    loginNeeded
      ? "- 当前页面像登录页。请先运行 `npm run douyin:login`，完成登录后再运行 `npm run douyin:poll`。"
      : "- 已读取页面可见内容。若识别作品数为 0，需要打开创作者后台作品管理/数据中心页面后重试，或调整页面解析规则。",
    "",
    "## 后续",
    "",
    "- 数据写入 `06_logs/douyin-videos.csv` 和 `06_logs/douyin-metrics-snapshots.csv`。",
    "- 这一步只读取自己的账号页面，不发布、不修改、不删除内容。",
    ""
  ];

  await writeFile(target, lines.join("\n"), "utf-8");
  return target;
};

const login = async ({ port, url }) => {
  await launchChrome({ port, url });
  await waitForChrome(port);
  console.log("Douyin Chrome profile opened.");
  console.log(`Profile: ${path.relative(ROOT, RUNTIME_DIR)}`);
  console.log("Please log in inside the opened Chrome window, then keep that login state for future polling.");
};

const poll = async ({ port, url, date, waitMs, keepOpen }) => {
  await mkdir(LOG_DIR, { recursive: true });
  await ensureCsv(VIDEOS_CSV, VIDEO_HEADERS);
  await ensureCsv(SNAPSHOTS_CSV, SNAPSHOT_HEADERS);
  await launchChrome({ port, url });
  await waitForChrome(port);

  const snapshotAt = isoNow();
  const pageData = await evaluatePage(port, url, waitMs);
  const rawPath = await writeRaw(date, pageData);
  const loginNeeded = isLikelyLoginPage(pageData);
  const extracted = loginNeeded ? [] : extractVideos(pageData, snapshotAt);

  await upsertVideos(extracted.map((item) => item.video), snapshotAt);
  await appendCsvRows(SNAPSHOTS_CSV, SNAPSHOT_HEADERS, extracted.map((item) => item.snapshot));
  const matchResult = await matchVideosToLedger();
  const reportPath = await writeReport({ date, pageData, rawPath, extracted, loginNeeded });

  console.log(`report=${path.relative(ROOT, reportPath)}`);
  console.log(`raw=${path.relative(ROOT, rawPath)}`);
  console.log(`videos=${extracted.length}`);
  console.log(`matched=${matchResult.matched}`);
  console.log(`login_needed=${loginNeeded ? "yes" : "no"}`);
  if (!keepOpen) {
    console.log("Chrome was left open for review. Close it manually when done.");
  }
};

const main = async () => {
  const options = parseArgs(process.argv);
  if (options.help) {
    printHelp();
    return;
  }

  if (options.command === "login") {
    await login(options);
    return;
  }

  if (options.command === "poll") {
    await poll(options);
    return;
  }

  throw new Error(`Unknown command: ${options.command}`);
};

await main();
