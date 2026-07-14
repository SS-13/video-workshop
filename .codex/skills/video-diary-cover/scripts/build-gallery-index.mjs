import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ROOT = process.cwd();
const SOURCE_ROOT = path.join(ROOT, "15_cover_gallery");
const OUTPUT_PATH = path.join(SOURCE_ROOT, "INDEX.md");

const parseTableRows = (text) => {
  const rows = [];
  for (const line of text.split("\n")) {
    if (!line.startsWith("|")) {
      continue;
    }
    const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
    if (cells[0] === "version" || cells.every((cell) => /^-+$/.test(cell))) {
      continue;
    }
    if (cells.length >= 6) {
      rows.push({
        version: cells[0],
        file: cells[1],
        route: cells[2],
        styleVersion: cells[3],
        title: cells[4],
        note: cells[5],
        result: cells[6] ?? ""
      });
      continue;
    }

    if (cells.length >= 4) {
      rows.push({
        version: cells[0],
        file: cells[1],
        route: "video-diary",
        styleVersion: "legacy",
        title: cells[2],
        note: cells[3],
        result: cells[4] ?? ""
      });
    }
  }
  return rows;
};

const readDateGallery = async (date) => {
  const indexPath = path.join(SOURCE_ROOT, date, "INDEX.md");
  try {
    const text = await readFile(indexPath, "utf8");
    return parseTableRows(text).map((row) => ({ date, ...row }));
  } catch (error) {
    if (error.code === "ENOENT") {
      return [];
    }
    throw error;
  }
};

const main = async () => {
  const dates = (await readdir(SOURCE_ROOT))
    .filter((entry) => DATE_RE.test(entry))
    .sort();

  const rows = [];
  for (const date of dates) {
    rows.push(...await readDateGallery(date));
  }

  const lines = [
    "# Cover Gallery Index",
    "",
    "This index is generated from `15_cover_gallery/` and is used by `video-diary-cover` as the cover design gallery.",
    "",
    "| preview | date | version | route | style | title | note |",
    "| --- | --- | --- | --- | --- | --- | --- |"
  ];

  for (const row of rows) {
    const previewPath = `./${row.date}/${row.file}`;
    const note = [row.note, row.result].filter(Boolean).join(" / ");
    lines.push(`| ![${row.date} ${row.version}](${previewPath}) | ${row.date} | ${row.version} | ${row.route} | ${row.styleVersion} | ${row.title} | ${note} |`);
  }

  await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
  await writeFile(OUTPUT_PATH, `${lines.join("\n")}\n`, "utf8");
  console.log(`gallery=${path.relative(ROOT, OUTPUT_PATH)}`);
  console.log(`items=${rows.length}`);
};

await main();
