import { mkdir, readFile, writeFile, appendFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import os from "node:os";

const ROOT = process.cwd();
const DEFAULT_BASE_TOKEN = "";
const DEFAULT_TABLE_ID = "";
const DEFAULT_INTERVAL_MS = 30_000;
const DEFAULT_LIMIT = 100;
const CODEX_BIN = process.env.CODEX_BIN ?? "codex";
const LOG_DIR = path.join(ROOT, "06_logs");
const WORKER_LOG_PATH = path.join(LOG_DIR, "feishu-worker.log");
const WORKER_STATUS_PATH = path.join(LOG_DIR, "feishu-worker-status.json");
const STARTED_AT = new Date().toISOString();
const contentTextPath = (stage, date, contentType = "video-diary", sequence = "001") => (
  path.join(ROOT, stage, date, contentType, `${sequence}.md`)
);

const maskIdentifier = (value) => {
  const text = String(value ?? "");
  if (text.length <= 8) {
    return text ? "configured" : "";
  }
  return `${text.slice(0, 4)}...${text.slice(-4)}`;
};

const workerState = {
  pid: process.pid,
  status: "starting",
  startedAt: STARTED_AT,
  updatedAt: STARTED_AT,
  mode: "",
  baseToken: "",
  tableId: "",
  intervalMs: DEFAULT_INTERVAL_MS,
  limit: DEFAULT_LIMIT,
  cycles: 0,
  totalProcessed: 0,
  lastHeartbeatAt: "",
  lastPollAt: "",
  lastCycleAt: "",
  lastProcessedAt: "",
  lastErrorAt: "",
  lastError: ""
};

const FIELD = {
  title: "标题",
  date: "日期",
  topicNumber: "话题序号",
  action: "动作",
  status: "状态",
  raw: "原始文案",
  candidate1: "脚本候选 1",
  candidate2: "脚本候选 2",
  candidate3: "脚本候选 3",
  selected: "选用脚本",
  finalScript: "最终脚本",
  localPath: "本地路径",
  note: "备注"
};

const ACTION = {
  recordIdea: "录入想法",
  generateScript: "生成脚本",
  regenerate: "重新生成"
};

const STATUS = {
  pending: "待处理",
  recorded: "已录入",
  pendingScript: "待生成脚本",
  scripted: "脚本已生成",
  selected: "已选择",
  error: "异常"
};

const parseArgs = (argv) => {
  const options = {
    baseToken: process.env.FEISHU_BASE_TOKEN ?? DEFAULT_BASE_TOKEN,
    tableId: process.env.FEISHU_TABLE_ID ?? DEFAULT_TABLE_ID,
    intervalMs: Number(process.env.FEISHU_WORKER_INTERVAL_MS ?? DEFAULT_INTERVAL_MS),
    limit: Number(process.env.FEISHU_WORKER_LIMIT ?? DEFAULT_LIMIT),
    model: process.env.FEISHU_SCRIPT_MODEL ?? "",
    once: false,
    dryRun: false,
    help: false
  };

  for (const arg of argv.slice(2)) {
    if (arg === "--once") {
      options.once = true;
      continue;
    }

    if (arg === "--dry-run") {
      options.dryRun = true;
      continue;
    }

    if (arg === "--help" || arg === "-h") {
      options.help = true;
      continue;
    }

    if (arg.startsWith("--interval=")) {
      options.intervalMs = Number(arg.split("=")[1]);
      continue;
    }

    if (arg.startsWith("--limit=")) {
      options.limit = Number(arg.split("=")[1]);
      continue;
    }

    if (arg.startsWith("--model=")) {
      options.model = arg.split("=").slice(1).join("=");
      continue;
    }

    if (arg.startsWith("--base-token=")) {
      options.baseToken = arg.split("=").slice(1).join("=");
      continue;
    }

    if (arg.startsWith("--table-id=")) {
      options.tableId = arg.split("=").slice(1).join("=");
    }
  }

  if (!Number.isFinite(options.intervalMs) || options.intervalMs < 5_000) {
    throw new Error("Interval must be at least 5000 ms.");
  }

  if (!Number.isInteger(options.limit) || options.limit < 1 || options.limit > 200) {
    throw new Error("Limit must be an integer from 1 to 200.");
  }

  return options;
};

const printHelp = () => {
  console.log(`Feishu remote script worker

Usage:
  node 09_tools/feishu-remote-script-worker.mjs --once
  node 09_tools/feishu-remote-script-worker.mjs

Options:
  --once                 Run one polling cycle and exit.
  --dry-run              Read Feishu records and print intended actions only.
  --interval=30000       Polling interval in milliseconds.
  --limit=100            Max records to read per cycle, 1-200.
  --model=gpt-5.5        Optional Codex model override if available locally.

Environment:
  FEISHU_BASE_TOKEN
  FEISHU_TABLE_ID
  FEISHU_SCRIPT_MODEL
  FEISHU_WORKER_INTERVAL_MS
  FEISHU_WORKER_LIMIT
  CODEX_BIN
`);
};

const runCommand = (command, args, {
  cwd = ROOT,
  env = {},
  input = "",
  timeoutMs = 120_000
} = {}) => new Promise((resolve, reject) => {
  const child = spawn(command, args, {
    cwd,
    env: {
      ...process.env,
      ...env
    },
    stdio: ["pipe", "pipe", "pipe"]
  });

  let stdout = "";
  let stderr = "";
  let finished = false;

  const timer = setTimeout(() => {
    if (finished) {
      return;
    }

    child.kill("SIGTERM");
    reject(new Error(`Command timed out: ${command} ${args.join(" ")}`));
  }, timeoutMs);

  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });

  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });

  child.on("error", (error) => {
    finished = true;
    clearTimeout(timer);
    reject(error);
  });

  child.on("close", (code) => {
    finished = true;
    clearTimeout(timer);

    if (code === 0) {
      resolve({ stdout, stderr });
      return;
    }

    reject(new Error([
      `Command failed (${code}): ${command} ${args.join(" ")}`,
      stderr.trim(),
      stdout.trim()
    ].filter(Boolean).join("\n")));
  });

  if (input) {
    child.stdin.write(input);
  }

  child.stdin.end();
});

const runLark = async (args, options = {}) => runCommand("lark-cli", args, {
  ...options,
  env: {
    LARK_CLI_NO_PROXY: "1",
    ...(options.env ?? {})
  }
});

const selectValue = (value) => {
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }

  return String(value ?? "");
};

const normalizeDate = (value) => {
  const raw = Array.isArray(value) ? value[0] : value;
  const match = String(raw ?? "").match(/\d{4}-\d{2}-\d{2}/);

  if (match) {
    return match[0];
  }

  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const formatTopicNumber = (value, fallbackIndex) => {
  const number = Number(value);
  const safeNumber = Number.isInteger(number) && number > 0 ? number : fallbackIndex;
  return {
    number: safeNumber,
    label: `S${String(safeNumber).padStart(2, "0")}`
  };
};

const buildTopicHeading = (topicNumber) => `## 话题 ${topicNumber}`;

const buildScriptHeading = (topicLabel, title) => `## ${topicLabel} ${title}`;

const findSectionRange = (content, headingPattern, nextHeadingPattern) => {
  const startMatch = headingPattern.exec(content);
  if (!startMatch) {
    return null;
  }

  const start = startMatch.index;
  const afterStart = start + startMatch[0].length;
  const rest = content.slice(afterStart);
  const nextMatch = nextHeadingPattern.exec(rest);
  const end = nextMatch ? afterStart + nextMatch.index : content.length;

  return { start, end };
};

const replaceSection = (content, range, replacement) => [
  content.slice(0, range.start).trimEnd(),
  replacement.trimEnd(),
  content.slice(range.end).trimStart()
].filter(Boolean).join("\n\n") + "\n";

const toFieldMap = (fields, row) => Object.fromEntries(
  fields.map((fieldName, index) => [fieldName, row[index]])
);

const listRecords = async (options) => {
  const { stdout } = await runLark([
    "base",
    "+record-list",
    "--as",
    "user",
    "--base-token",
    options.baseToken,
    "--table-id",
    options.tableId,
    "--limit",
    String(options.limit),
    "--format",
    "json"
  ]);

  const payload = JSON.parse(stdout);
  const fields = payload.data?.fields ?? [];
  const rows = payload.data?.data ?? [];
  const recordIds = payload.data?.record_id_list ?? [];

  return rows.map((row, index) => ({
    recordId: recordIds[index],
    fields: toFieldMap(fields, row)
  }));
};

const updateRecord = async (record, patch, options) => {
  if (options.dryRun) {
    await logEvent("info", "dry-run update record", {
      recordId: record.recordId,
      patch
    });
    return;
  }

  await runLark([
    "base",
    "+record-upsert",
    "--as",
    "user",
    "--base-token",
    options.baseToken,
    "--table-id",
    options.tableId,
    "--record-id",
    record.recordId,
    "--json",
    JSON.stringify(patch),
    "--format",
    "json"
  ]);
};

const ensureDayWorkspace = async (date, options) => {
  if (options.dryRun) {
    await logEvent("info", "dry-run ensure day workspace", { date });
    return;
  }

  await runCommand(process.execPath, [path.join(ROOT, "09_tools", "new-day.mjs"), date], {
    cwd: ROOT,
    timeoutMs: 60_000
  });
};

const readTextFile = async (filePath) => {
  try {
    return await readFile(filePath, "utf-8");
  } catch (error) {
    if (error.code === "ENOENT") {
      return "";
    }

    throw error;
  }
};

const appendRawIdea = async (record, options) => {
  const fields = record.fields;
  const date = normalizeDate(fields[FIELD.date]);
  const title = String(fields[FIELD.title] ?? "未命名话题");
  const raw = String(fields[FIELD.raw] ?? "");
  const topic = formatTopicNumber(fields[FIELD.topicNumber], 1);
  const inboxPath = contentTextPath("01_inbox", date);
  const marker = `<!-- feishu-record:${record.recordId}:raw -->`;
  const markerEnd = `<!-- feishu-record:${record.recordId}:raw-end -->`;
  const localPath = `01_inbox/${date}/video-diary/001.md`;

  if (!raw.trim()) {
    throw new Error("原始文案为空，无法录入。");
  }

  await ensureDayWorkspace(date, options);

  const existing = await readTextFile(inboxPath);
  if (existing.includes(marker)) {
    return { date, title, raw, topic, localPath, changed: false };
  }
  const attributedExisting = existing.replace(
    /^-\s*灵感来源：待确认\s*$/m,
    "- 灵感来源：生活输入"
  );

  const block = [
    buildTopicHeading(topic.number),
    `- 时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
    "- 灵感来源：生活输入",
    "- Sparkling ID：-",
    "- 原始口述：",
    "",
    marker,
    raw,
    markerEnd,
    "",
    "- 来源：飞书远程入口",
    `- 飞书记录：${record.recordId}`,
    "- 录制状态：未生成脚本"
  ].join("\n");

  if (options.dryRun) {
    await logEvent("info", "dry-run append raw idea", {
      recordId: record.recordId,
      localPath,
      title
    });
    return { date, title, raw, topic, localPath, changed: true };
  }

  const topicHeadingRe = new RegExp(`^##\\s+话题\\s+${topic.number}\\b.*$`, "m");
  const nextTopicRe = /^##\s+话题\s+\d+\b.*$/m;
  const range = findSectionRange(attributedExisting, topicHeadingRe, nextTopicRe);
  const nextContent = range
    ? replaceSection(attributedExisting, range, block)
    : `${attributedExisting.trimEnd()}\n\n${block}\n`;

  await writeFile(inboxPath, nextContent);
  return { date, title, raw, topic, localPath, changed: true };
};

const readStyleGuide = async () => {
  const localStylePath = path.join(ROOT, "10_skills", "personal-speaking-style", "SKILL.md");
  const publicStylePath = path.join(ROOT, "00_system", "defaults", "speaking-style.md");
  const localStyle = await readTextFile(localStylePath);
  if (localStyle.trim()) {
    return localStyle;
  }
  return readTextFile(publicStylePath);
};

const buildScriptPrompt = async ({ date, title, raw, topic }) => {
  const styleGuide = await readStyleGuide();

  return `你是 Video Workshop 里的 Script Agent。

任务：把一条飞书远程录入的原始想法，改写成一个可以直接放进提词器 APP 的口播脚本。

必须遵守：
- 只生成一个脚本段落，对应 ${topic.label}。
- 保留原始意思、原始顺序和口语感。
- 不写公众号文章，不写营销短视频腔，不制造强 hook。
- 少解释动机，多说具体事实。
- 不替用户拔高主题，不替用户制造情绪。
- 句子短一点，适合直接读出来。
- 不要编造原始文案里没有的信息。
- 输出只要 Markdown 脚本正文，不要解释你的处理过程。

输出格式必须是：

## ${topic.label} ${title}

### 一句话核心

...

### 提词器文案

\`\`\`text
...
\`\`\`

### 拍摄提示

- 预计时长：
- 情绪：
- 必须说到：
- 结尾方式：

个人口播风格参考：

${styleGuide}

原始信息：
- 日期：${date}
- 话题序号：${topic.label}
- 标题：${title}

原始文案如下：

${raw}
`;
};

const ensureLogDir = async () => {
  await mkdir(LOG_DIR, { recursive: true });
};

const safeStringifyDetails = (details) => {
  const keys = Object.keys(details ?? {});
  if (keys.length === 0) {
    return "";
  }

  return ` ${JSON.stringify(details)}`;
};

const logEvent = async (level, message, details = {}) => {
  const ts = new Date().toISOString();
  const line = `[${ts}] ${level.toUpperCase()} ${message}${safeStringifyDetails(details)}`;

  console.log(line);

  try {
    await ensureLogDir();
    await appendFile(WORKER_LOG_PATH, `${line}\n`);
  } catch (error) {
    console.error("failed to write worker log:", error);
  }
};

const writeWorkerStatus = async (patch = {}) => {
  const now = new Date().toISOString();
  Object.assign(workerState, patch, {
    updatedAt: now,
    lastHeartbeatAt: now
  });

  try {
    await ensureLogDir();
    await writeFile(WORKER_STATUS_PATH, `${JSON.stringify(workerState, null, 2)}\n`);
  } catch (error) {
    console.error("failed to write worker status:", error);
  }
};

const generateScript = async (context, options) => {
  const prompt = await buildScriptPrompt(context);
  const outputPath = path.join(
    os.tmpdir(),
    `feishu-script-${context.date}-${context.topic.label}-${Date.now()}.md`
  );

  if (options.dryRun) {
    await logEvent("info", "dry-run generate script with Codex", {
      date: context.date,
      topic: context.topic.label,
      title: context.title
    });
    return `## ${context.topic.label} ${context.title}

### 一句话核心

dry-run：这里会由 Codex 生成脚本。

### 提词器文案

\`\`\`text
dry-run：这里会回填正式口播脚本。
\`\`\`

### 拍摄提示

- 预计时长：1-2 分钟
- 情绪：自然
- 必须说到：
- 结尾方式：自然收住
`;
  }

  const args = [
    "exec",
    "--skip-git-repo-check",
    "--ephemeral",
    "--sandbox",
    "read-only",
    "-C",
    ROOT,
    "-o",
    outputPath
  ];

  if (options.model) {
    args.push("-m", options.model);
  }

  args.push("-");

  await runCommand(CODEX_BIN, args, {
    cwd: ROOT,
    input: prompt,
    timeoutMs: 240_000
  });

  const script = (await readTextFile(outputPath)).trim();
  if (!script) {
    throw new Error("Codex 没有返回脚本内容。");
  }

  return script;
};

const upsertScriptBlock = async (record, context, script, options) => {
  const scriptPath = contentTextPath("02_scripts", context.date);
  const localPath = `02_scripts/${context.date}/video-diary/001.md`;
  const marker = `<!-- feishu-script:${record.recordId}:start -->`;
  const markerEnd = `<!-- feishu-script:${record.recordId}:end -->`;
  const block = `${marker}
${script.trim()}
${markerEnd}`;

  if (options.dryRun) {
    await logEvent("info", "dry-run upsert script block", {
      recordId: record.recordId,
      localPath,
      title: context.title
    });
    return localPath;
  }

  const existing = await readTextFile(scriptPath);
  const markerPattern = new RegExp(`${escapeRegExp(marker)}[\\s\\S]*?${escapeRegExp(markerEnd)}`);
  const scriptHeadingRe = new RegExp(`^##\\s+${escapeRegExp(context.topic.label)}\\b.*$`, "m");
  const nextScriptRe = /^##\s+(?:S\d+\b|自动剪辑要求\b).*$/m;
  const range = findSectionRange(existing, scriptHeadingRe, nextScriptRe);
  const nextContent = existing.includes(marker)
    ? existing.replace(markerPattern, block)
    : range
      ? replaceSection(existing, range, block)
      : `${existing.trimEnd()}\n\n${block}\n`;

  await writeFile(scriptPath, nextContent);
  return localPath;
};

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const shouldRecordIdea = (record) => {
  const action = selectValue(record.fields[FIELD.action]);
  const status = selectValue(record.fields[FIELD.status]);
  return action === ACTION.recordIdea && status === STATUS.pending;
};

const shouldGenerateScript = (record) => {
  const action = selectValue(record.fields[FIELD.action]);
  const status = selectValue(record.fields[FIELD.status]);
  const allowedStatus = new Set([
    STATUS.pending,
    STATUS.recorded,
    STATUS.pendingScript,
    STATUS.error
  ]);

  if (status === STATUS.pendingScript) {
    return true;
  }

  return [ACTION.generateScript, ACTION.regenerate].includes(action) &&
    allowedStatus.has(status);
};

const processRecordIdea = async (record, options) => {
  const context = await appendRawIdea(record, options);
  await updateRecord(record, {
    [FIELD.status]: STATUS.recorded,
    [FIELD.localPath]: context.localPath,
    [FIELD.note]: context.changed
      ? "已同步到本地 01_inbox。需要生成脚本时，把动作改为“生成脚本”。"
      : "本地 01_inbox 已存在这条记录。需要生成脚本时，把动作改为“生成脚本”。"
  }, options);

  await logEvent("info", "recorded raw idea", {
    recordId: record.recordId,
    localPath: context.localPath,
    changed: context.changed
  });
  await writeWorkerStatus({
    lastProcessedAt: new Date().toISOString()
  });
};

const processGenerateScript = async (record, options) => {
  const context = await appendRawIdea(record, options);
  const script = await generateScript(context, options);
  const scriptLocalPath = await upsertScriptBlock(record, context, script, options);

  await updateRecord(record, {
    [FIELD.status]: STATUS.scripted,
    [FIELD.candidate1]: script,
    [FIELD.selected]: "候选 1",
    [FIELD.finalScript]: script,
    [FIELD.localPath]: `${context.localPath}\n${scriptLocalPath}`,
    [FIELD.note]: `脚本已生成并回填。生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`
  }, options);

  await logEvent("info", "generated and synced script", {
    recordId: record.recordId,
    localPath: scriptLocalPath,
    title: context.title
  });
  await writeWorkerStatus({
    lastProcessedAt: new Date().toISOString()
  });
};

const markError = async (record, error, options) => {
  const message = error instanceof Error ? error.message : String(error);

  try {
    await updateRecord(record, {
      [FIELD.status]: STATUS.error,
      [FIELD.note]: `处理失败：${message.slice(0, 900)}`
    }, options);
  } catch (updateError) {
    await logEvent("error", "failed to mark record error", {
      recordId: record.recordId,
      error: updateError instanceof Error ? updateError.message : String(updateError)
    });
  }
};

const runOnce = async (options) => {
  await logEvent("info", "polling Feishu records", {
    baseToken: maskIdentifier(options.baseToken),
    tableId: maskIdentifier(options.tableId),
    limit: options.limit
  });
  await writeWorkerStatus({
    status: "polling",
    lastPollAt: new Date().toISOString()
  });

  const records = await listRecords(options);
  let processed = 0;

  for (const record of records) {
    try {
      if (shouldRecordIdea(record)) {
        await logEvent("info", "received record idea task", {
          recordId: record.recordId,
          title: record.fields[FIELD.title] ?? ""
        });
        await processRecordIdea(record, options);
        processed += 1;
        continue;
      }

      if (shouldGenerateScript(record)) {
        await logEvent("info", "received script generation task", {
          recordId: record.recordId,
          title: record.fields[FIELD.title] ?? ""
        });
        await processGenerateScript(record, options);
        processed += 1;
      }
    } catch (error) {
      processed += 1;
      await logEvent("error", "record processing failed", {
        recordId: record.recordId,
        error: error instanceof Error ? error.message : String(error)
      });
      await writeWorkerStatus({
        status: "error",
        lastErrorAt: new Date().toISOString(),
        lastError: error instanceof Error ? error.message : String(error)
      });
      await markError(record, error, options);
    }
  }

  workerState.cycles += 1;
  workerState.totalProcessed += processed;
  await writeWorkerStatus({
    status: "idle",
    lastCycleAt: new Date().toISOString(),
    cycles: workerState.cycles,
    totalProcessed: workerState.totalProcessed
  });
  await logEvent("info", "cycle complete", { processed });
};

let stopRequested = false;
let stopSleepResolver = null;

const sleep = (ms) => new Promise((resolve) => {
  stopSleepResolver = resolve;
  setTimeout(() => {
    stopSleepResolver = null;
    resolve();
  }, ms);
});

const main = async () => {
  const options = parseArgs(process.argv);

  if (options.help) {
    printHelp();
    return;
  }

  if (!options.baseToken || !options.tableId) {
    throw new Error(
      "Missing Feishu configuration. Set FEISHU_BASE_TOKEN and FEISHU_TABLE_ID "
      + "or pass --base-token and --table-id."
    );
  }

  await ensureLogDir();
  await writeWorkerStatus({
    status: "running",
    mode: options.dryRun ? "dry-run" : "live",
    baseToken: maskIdentifier(options.baseToken),
    tableId: maskIdentifier(options.tableId),
    intervalMs: options.intervalMs,
    limit: options.limit
  });
  await logEvent("info", "Feishu worker started", {
    pid: process.pid,
    baseToken: maskIdentifier(options.baseToken),
    tableId: maskIdentifier(options.tableId),
    mode: options.dryRun ? "dry-run" : "live",
    intervalMs: options.intervalMs
  });

  if (options.once) {
    await runOnce(options);
    await writeWorkerStatus({ status: "stopped" });
    await logEvent("info", "Feishu worker stopped after one cycle", { pid: process.pid });
    return;
  }

  const stop = async (signal) => {
    if (stopRequested) {
      return;
    }

    stopRequested = true;
    await writeWorkerStatus({ status: "stopping" });
    await logEvent("info", "Feishu worker stopping", { signal, pid: process.pid });

    if (stopSleepResolver) {
      stopSleepResolver();
      stopSleepResolver = null;
    }
  };

  process.on("SIGINT", () => {
    void stop("SIGINT");
  });

  process.on("SIGTERM", () => {
    void stop("SIGTERM");
  });

  while (true) {
    await runOnce(options);

    if (stopRequested) {
      await writeWorkerStatus({ status: "stopped" });
      await logEvent("info", "Feishu worker stopped", { pid: process.pid });
      return;
    }

    await sleep(options.intervalMs);

    if (stopRequested) {
      await writeWorkerStatus({ status: "stopped" });
      await logEvent("info", "Feishu worker stopped", { pid: process.pid });
      return;
    }
  }
};

try {
  await main();
} catch (error) {
  await logEvent("error", "Feishu worker crashed", {
    error: error instanceof Error ? error.message : String(error)
  });
  await writeWorkerStatus({
    status: "crashed",
    lastErrorAt: new Date().toISOString(),
    lastError: error instanceof Error ? error.message : String(error)
  });
  process.exitCode = 1;
}
