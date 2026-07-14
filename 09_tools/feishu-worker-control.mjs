import { readFile, writeFile, appendFile, unlink } from "node:fs/promises";
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";

const ROOT = process.cwd();
const LOG_DIR = path.join(ROOT, "06_logs");
const PID_PATH = path.join(LOG_DIR, "feishu-worker.pid");
const CAFFEINATE_PID_PATH = path.join(LOG_DIR, "feishu-worker-caffeinate.pid");
const LOG_PATH = path.join(LOG_DIR, "feishu-worker.log");
const STATUS_PATH = path.join(LOG_DIR, "feishu-worker-status.json");
const WORKER_PATH = path.join(ROOT, "09_tools", "feishu-remote-script-worker.mjs");

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

const isProcessRunning = (pid) => {
  if (!pid) {
    return false;
  }

  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

const getPid = async () => {
  const value = (await readText(PID_PATH)).trim();
  const pid = Number(value);
  return Number.isInteger(pid) && pid > 0 ? pid : null;
};

const readStatus = async () => {
  const content = await readText(STATUS_PATH);
  if (!content.trim()) {
    return null;
  }

  try {
    return JSON.parse(content);
  } catch {
    return null;
  }
};

const printHelp = () => {
  console.log(`Feishu worker control

Usage:
  node 09_tools/feishu-worker-control.mjs start
  node 09_tools/feishu-worker-control.mjs stop
  node 09_tools/feishu-worker-control.mjs status
  node 09_tools/feishu-worker-control.mjs logs [--lines=40]
  node 09_tools/feishu-worker-control.mjs watch
  node 09_tools/feishu-worker-control.mjs go-out
  node 09_tools/feishu-worker-control.mjs come-back

Examples:
  npm run feishu-worker:start
  npm run feishu-worker:status
  npm run feishu-worker:stop
  npm run go-out
  npm run come-back
`);
};

const start = async ({ quiet = false } = {}) => {
  const existingPid = await getPid();
  if (isProcessRunning(existingPid)) {
    if (!quiet) {
      console.log(`Feishu worker already running. pid=${existingPid}`);
    }
    return existingPid;
  }

  const out = await appendFile(LOG_PATH, "");
  void out;

  const child = spawn(process.execPath, [WORKER_PATH], {
    cwd: ROOT,
    detached: true,
    stdio: ["ignore", "ignore", "ignore"],
    env: {
      ...process.env,
      LARK_CLI_NO_PROXY: "1"
    }
  });

  child.unref();
  await writeFile(PID_PATH, `${child.pid}\n`);
  if (!quiet) {
    console.log(`Feishu worker started. pid=${child.pid}`);
    console.log(`Log: ${path.relative(ROOT, LOG_PATH)}`);
  }
  return child.pid;
};

const stop = async ({ quiet = false } = {}) => {
  const pid = await getPid();

  if (!pid || !isProcessRunning(pid)) {
    if (!quiet) {
      console.log("Feishu worker is not running.");
    }
    try {
      await unlink(PID_PATH);
    } catch {
      // Ignore stale pid cleanup failures.
    }
    return false;
  }

  process.kill(pid, "SIGTERM");
  if (!quiet) {
    console.log(`Feishu worker stop signal sent. pid=${pid}`);
  }
  return true;
};

const status = async () => {
  const pid = await getPid();
  const running = isProcessRunning(pid);
  const workerStatus = await readStatus();

  console.log(`Running: ${running ? "yes" : "no"}`);
  console.log(`PID: ${pid ?? "none"}`);

  if (!workerStatus) {
    console.log("Status file: not found");
    return;
  }

  console.log(`Worker status: ${workerStatus.status}`);
  console.log(`Mode: ${workerStatus.mode}`);
  console.log(`Started at: ${workerStatus.startedAt}`);
  console.log(`Updated at: ${workerStatus.updatedAt}`);
  console.log(`Last poll: ${workerStatus.lastPollAt || "none"}`);
  console.log(`Last cycle: ${workerStatus.lastCycleAt || "none"}`);
  console.log(`Cycles: ${workerStatus.cycles}`);
  console.log(`Total processed: ${workerStatus.totalProcessed}`);

  if (workerStatus.lastError) {
    console.log(`Last error: ${workerStatus.lastError}`);
  }
};

const getCaffeinatePid = async () => {
  const value = (await readText(CAFFEINATE_PID_PATH)).trim();
  const pid = Number(value);
  return Number.isInteger(pid) && pid > 0 ? pid : null;
};

const startCaffeinate = async ({ quiet = false } = {}) => {
  const existingPid = await getCaffeinatePid();
  if (isProcessRunning(existingPid)) {
    if (!quiet) {
      console.log(`Caffeinate already running. pid=${existingPid}`);
    }
    return existingPid;
  }

  const child = spawn("/usr/bin/caffeinate", ["-dimsu"], {
    cwd: ROOT,
    detached: true,
    stdio: ["ignore", "ignore", "ignore"]
  });

  child.unref();
  await writeFile(CAFFEINATE_PID_PATH, `${child.pid}\n`);
  if (!quiet) {
    console.log(`Caffeinate started. pid=${child.pid}`);
  }
  return child.pid;
};

const stopCaffeinate = async ({ quiet = false } = {}) => {
  const pid = await getCaffeinatePid();

  if (!pid || !isProcessRunning(pid)) {
    if (!quiet) {
      console.log("Caffeinate is not running.");
    }
    try {
      await unlink(CAFFEINATE_PID_PATH);
    } catch {
      // Ignore stale pid cleanup failures.
    }
    return false;
  }

  process.kill(pid, "SIGTERM");
  if (!quiet) {
    console.log(`Caffeinate stop signal sent. pid=${pid}`);
  }
  return true;
};

const sleep = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
});

const goOut = async () => {
  const caffeinatePid = await startCaffeinate({ quiet: true });
  const workerPid = await start({ quiet: true });

  await sleep(4000);

  const workerRunning = isProcessRunning(await getPid());
  const caffeinateRunning = isProcessRunning(await getCaffeinatePid());
  const workerStatus = await readStatus();

  console.log("出门监听已设置。");
  console.log(`Caffeinate: ${caffeinateRunning ? "running" : "not running"} pid=${caffeinatePid}`);
  console.log(`Feishu worker: ${workerRunning ? "running" : "not running"} pid=${workerPid}`);

  if (workerStatus) {
    console.log(`Worker status: ${workerStatus.status}`);
    console.log(`Last poll: ${workerStatus.lastPollAt || "none"}`);
    console.log(`Cycles: ${workerStatus.cycles}`);
  }

  console.log(`Log: ${path.relative(ROOT, LOG_PATH)}`);
};

const comeBack = async () => {
  await stop({ quiet: true });
  await stopCaffeinate({ quiet: true });
  await sleep(4000);

  const workerRunning = isProcessRunning(await getPid());
  const caffeinateRunning = isProcessRunning(await getCaffeinatePid());

  console.log("回家模式已收尾。");
  console.log(`Feishu worker: ${workerRunning ? "still running" : "stopped"}`);
  console.log(`Caffeinate: ${caffeinateRunning ? "still running" : "stopped"}`);
};

const logs = async (lines = 40) => {
  const content = await readText(LOG_PATH);
  const output = content.split(/\r?\n/).filter(Boolean).slice(-lines).join("\n");
  console.log(output || "No worker logs yet.");
};

const watch = async () => {
  console.log("Watching Feishu worker log. Press Ctrl+C to stop watching.");
  let offset = 0;

  if (existsSync(LOG_PATH)) {
    const current = await readText(LOG_PATH);
    offset = current.length;
    const recent = current.split(/\r?\n/).filter(Boolean).slice(-20).join("\n");
    if (recent) {
      console.log(recent);
    }
  }

  setInterval(async () => {
    const content = await readText(LOG_PATH);
    if (content.length <= offset) {
      return;
    }

    const next = content.slice(offset);
    offset = content.length;
    process.stdout.write(next);
  }, 1000);
};

const main = async () => {
  const [command, ...args] = process.argv.slice(2);

  if (!command || command === "help" || command === "--help" || command === "-h") {
    printHelp();
    return;
  }

  if (command === "start") {
    await start();
    return;
  }

  if (command === "stop") {
    await stop();
    return;
  }

  if (command === "go-out") {
    await goOut();
    return;
  }

  if (command === "come-back") {
    await comeBack();
    return;
  }

  if (command === "status") {
    await status();
    return;
  }

  if (command === "logs") {
    const linesArg = args.find((arg) => arg.startsWith("--lines="));
    const lines = linesArg ? Number(linesArg.split("=")[1]) : 40;
    await logs(Number.isFinite(lines) ? lines : 40);
    return;
  }

  if (command === "watch") {
    await watch();
    return;
  }

  throw new Error(`Unknown command: ${command}`);
};

await main();
