import path from "node:path";
import { spawn } from "node:child_process";

const ROOT = process.cwd();
const NODE_BIN = process.env.NODE_BIN || process.execPath;
const RENDER_SCRIPT = path.join(ROOT, ".codex/skills/video-diary-cover/scripts/render-pencil-html.mjs");

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const options = {
    input: "",
    date: "",
    outputName: "",
    scale: "2"
  };
  const keyMap = {
    "output-name": "outputName"
  };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) {
      continue;
    }
    const rawKey = arg.slice(2);
    const key = keyMap[rawKey] || rawKey;
    const value = args[index + 1];
    if (value && !value.startsWith("--")) {
      options[key] = value;
      index += 1;
      continue;
    }
    options[key] = "true";
  }

  if (!options.input) {
    throw new Error("Missing --input path/to/exported-frame.html");
  }
  if (!options.date) {
    throw new Error("Missing --date YYYY-MM-DD");
  }
  if (!options.outputName) {
    throw new Error("Missing --output-name final-cover-name.png");
  }

  return options;
};

const run = (cmd, args) => new Promise((resolve, reject) => {
  const child = spawn(cmd, args, {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"]
  });

  let stdout = "";
  let stderr = "";

  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });

  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });

  child.on("error", reject);
  child.on("close", (code) => {
    if (code === 0) {
      resolve({ stdout, stderr });
      return;
    }
    reject(new Error(`Command failed with code ${code}\n${stderr || stdout}`));
  });
});

const main = async () => {
  const options = parseArgs(process.argv);
  const outputPath = path.join("05_exports", options.date, options.outputName);
  const args = [
    RENDER_SCRIPT,
    "--input",
    options.input,
    "--output",
    outputPath,
    "--scale",
    options.scale || "2"
  ];

  const result = await run(NODE_BIN, args);
  process.stdout.write(result.stdout);
  if (result.stderr.trim()) {
    process.stderr.write(result.stderr);
  }
  console.log(`final=${outputPath}`);
};

await main();
