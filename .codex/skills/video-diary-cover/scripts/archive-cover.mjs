import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const IMAGE_EXT_RE = /\.(jpg|jpeg|png|webp)$/i;

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const date = args.find((arg) => DATE_RE.test(arg));
  const sourceIndex = args.indexOf("--source");
  const titleIndex = args.indexOf("--title");
  const noteIndex = args.indexOf("--note");
  const routeIndex = args.indexOf("--route");
  const styleIndex = args.indexOf("--style-version");

  if (!date) {
    throw new Error("Usage: npm run archive-cover -- YYYY-MM-DD --source path/to/cover.jpg");
  }

  const source = sourceIndex >= 0 ? args[sourceIndex + 1] : undefined;
  if (!source) {
    throw new Error("Missing --source path.");
  }

  return {
    date,
    source,
    title: titleIndex >= 0 ? args[titleIndex + 1] : "",
    note: noteIndex >= 0 ? args[noteIndex + 1] : "",
    route: routeIndex >= 0 ? args[routeIndex + 1] : "",
    styleVersion: styleIndex >= 0 ? args[styleIndex + 1] : ""
  };
};

const getNextVersion = async (dir) => {
  try {
    const entries = await readdir(dir);
    const versions = entries
      .map((entry) => entry.match(/^v(\d{2})_/))
      .filter(Boolean)
      .map((match) => Number(match[1]));

    return versions.length ? Math.max(...versions) + 1 : 1;
  } catch (error) {
    if (error.code === "ENOENT") {
      return 1;
    }

    throw error;
  }
};

const tableCell = (value) => String(value || "").replaceAll("|", "\\|").trim();

const normalizeExistingIndex = (existing) => {
  const header = "| version | file | route | style_version | title | note |\n| --- | --- | --- | --- | --- | --- |\n";
  const rows = [];

  for (const line of existing.split("\n")) {
    if (!line.startsWith("|")) {
      continue;
    }
    if (line.includes("---") || line.includes("version")) {
      continue;
    }

    const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
    if (cells.length >= 6) {
      rows.push(`| ${cells.map(tableCell).slice(0, 6).join(" | ")} |`);
      continue;
    }
    if (cells.length >= 4) {
      rows.push(`| ${tableCell(cells[0])} | ${tableCell(cells[1])} | video-diary | legacy | ${tableCell(cells[2])} | ${tableCell(cells[3])} |`);
    }
  }

  return `${header}${rows.join("\n")}${rows.length ? "\n" : ""}`;
};

const appendIndex = async (indexPath, row) => {
  const header = "| version | file | route | style_version | title | note |\n| --- | --- | --- | --- | --- | --- |\n";

  try {
    const existing = await readFile(indexPath, "utf8");
    const normalized = existing.includes("style_version") ? existing : normalizeExistingIndex(existing);
    const prefix = normalized.startsWith("| version |") ? "" : header;
    const body = normalized.endsWith("\n") ? normalized : `${normalized}\n`;
    await writeFile(indexPath, `${prefix}${body}${row}`);
    return;
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }

    await writeFile(indexPath, `${header}${row}`);
  }
};

const main = async () => {
  const { date, source, title, note, route, styleVersion } = parseArgs(process.argv);
  const root = process.cwd();
  const sourcePath = path.resolve(root, source);
  const extension = path.extname(sourcePath);

  if (!IMAGE_EXT_RE.test(extension)) {
    throw new Error("Cover source must be an image file.");
  }

  const galleryDir = path.join(root, "15_cover_gallery", date);
  await mkdir(galleryDir, { recursive: true });

  const version = await getNextVersion(galleryDir);
  const versionLabel = `v${String(version).padStart(2, "0")}`;
  const outputName = `${versionLabel}_${date}_cover${extension.toLowerCase()}`;
  const outputPath = path.join(galleryDir, outputName);

  await copyFile(sourcePath, outputPath);

  const indexPath = path.join(galleryDir, "INDEX.md");
  const safeTitle = tableCell(title);
  const safeNote = tableCell(note);
  const safeRoute = tableCell(route);
  const safeStyleVersion = tableCell(styleVersion);
  const row = `| ${versionLabel} | ${outputName} | ${safeRoute} | ${safeStyleVersion} | ${safeTitle} | ${safeNote} |\n`;
  await appendIndex(indexPath, row);

  console.log(`cover=${path.relative(root, outputPath)}`);
  console.log(`index=${path.relative(root, indexPath)}`);
};

await main();
