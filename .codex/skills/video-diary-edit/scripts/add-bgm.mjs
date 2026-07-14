import { access, mkdir, readdir } from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DEFAULT_BGM = "11_templates/audio/bgm/quiet-documentary-the-mountain.mp3";
const DEFAULT_VOLUME = 0.16;
const DEFAULT_FADE_IN = 0.8;
const DEFAULT_FADE_OUT = 1.2;

const parseNumberFlag = (args, name, defaultValue) => {
  const inline = args.find((arg) => arg.startsWith(`--${name}=`));
  const index = args.indexOf(`--${name}`);
  const rawValue = inline?.split("=")[1] ?? (index >= 0 ? args[index + 1] : undefined);

  if (rawValue === undefined) {
    return defaultValue;
  }

  const value = Number(rawValue);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`--${name} must be a non-negative number.`);
  }

  return value;
};

const parseStringFlag = (args, name) => {
  const inline = args.find((arg) => arg.startsWith(`--${name}=`));
  const index = args.indexOf(`--${name}`);
  return inline?.split("=")[1] ?? (index >= 0 ? args[index + 1] : undefined);
};

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const date = args.find((arg) => DATE_RE.test(arg));

  if (!date) {
    throw new Error("Usage: npm run add-bgm -- YYYY-MM-DD [--bgm path/to/bgm.mp3] [--input path/to/video.mp4]");
  }

  return {
    date,
    input: parseStringFlag(args, "input"),
    bgm: parseStringFlag(args, "bgm") ?? DEFAULT_BGM,
    output: parseStringFlag(args, "output"),
    volume: parseNumberFlag(args, "volume", DEFAULT_VOLUME),
    fadeIn: parseNumberFlag(args, "fade-in", DEFAULT_FADE_IN),
    fadeOut: parseNumberFlag(args, "fade-out", DEFAULT_FADE_OUT)
  };
};

const run = (command, args) => new Promise((resolve, reject) => {
  const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";

  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });

  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });

  child.on("error", reject);
  child.on("close", (code) => {
    if (code === 0) {
      resolve({ stdout, stderr });
      return;
    }

    reject(new Error(stderr.trim() || `${command} exited with code ${code}`));
  });
});

const assertReadable = async (filePath, label) => {
  try {
    await access(filePath, constants.R_OK);
  } catch {
    throw new Error(`${label} not found or unreadable: ${filePath}`);
  }
};

const getDuration = async (filePath) => {
  const { stdout } = await run("ffprobe", [
    "-v", "error",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1",
    filePath
  ]);

  const duration = Number(stdout.trim());
  if (!Number.isFinite(duration) || duration <= 0) {
    throw new Error(`Cannot read duration: ${filePath}`);
  }

  return duration;
};

const findDefaultInput = async (root, date) => {
  const exportDir = path.join(root, "05_exports", date);
  const files = await readdir(exportDir);
  const candidates = files
    .filter((file) => file.endsWith(".mp4"))
    .filter((file) => file.includes("video-diary"))
    .filter((file) => !file.includes("_with-bgm"))
    .sort((left, right) => {
      const leftFinal = left.includes("_transcribed") ? 1 : 0;
      const rightFinal = right.includes("_transcribed") ? 1 : 0;
      return leftFinal - rightFinal || left.localeCompare(right, "zh-Hans-CN", { numeric: true });
    });

  if (!candidates.length) {
    throw new Error(`No final video found in ${path.relative(root, exportDir)}.`);
  }

  return path.join(exportDir, candidates[0]);
};

const getOutputPath = (inputPath, explicitOutput) => {
  if (explicitOutput) {
    return path.resolve(process.cwd(), explicitOutput);
  }

  const parsed = path.parse(inputPath);
  return path.join(parsed.dir, `${parsed.name}_with-bgm${parsed.ext}`);
};

const main = async () => {
  const root = process.cwd();
  const args = parseArgs(process.argv);
  const bgmPath = path.resolve(root, args.bgm);
  const inputPath = args.input ? path.resolve(root, args.input) : await findDefaultInput(root, args.date);
  const outputPath = getOutputPath(inputPath, args.output);

  await assertReadable(inputPath, "Input video");
  await assertReadable(bgmPath, "BGM file");
  await mkdir(path.dirname(outputPath), { recursive: true });

  const videoDuration = await getDuration(inputPath);
  const fadeOutStart = Math.max(0, videoDuration - args.fadeOut);
  const filter = [
    `[1:a]volume=${args.volume},`,
    `afade=t=in:st=0:d=${args.fadeIn},`,
    `afade=t=out:st=${fadeOutStart.toFixed(3)}:d=${args.fadeOut}[bgm];`,
    "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]"
  ].join("");

  await run("ffmpeg", [
    "-y",
    "-i", inputPath,
    "-stream_loop", "-1",
    "-i", bgmPath,
    "-filter_complex", filter,
    "-map", "0:v:0",
    "-map", "[a]",
    "-c:v", "copy",
    "-c:a", "aac",
    "-b:a", "192k",
    "-shortest",
    outputPath
  ]);

  console.log(`input=${path.relative(root, inputPath)}`);
  console.log(`bgm=${path.relative(root, bgmPath)}`);
  console.log(`output=${path.relative(root, outputPath)}`);
  console.log(`duration=${videoDuration.toFixed(2)}s`);
  console.log(`volume=${args.volume}`);
};

try {
  await main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
