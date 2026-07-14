import { access, mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import os from "node:os";
import { writeFile } from "node:fs/promises";

const ROOT = process.cwd();
const DEFAULT_OUTPUT_DIR = "11_templates/pencil-cover-demos";
const CHROME_CANDIDATES = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium"
];

const parseArgs = (argv) => {
  const args = argv.slice(2);
  const options = {
    input: "",
    output: "",
    selector: "[data-pencil-id]",
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
    throw new Error("Missing --input path/to/exported.html");
  }

  return options;
};

const resolveChromePath = async () => {
  for (const candidate of CHROME_CANDIDATES) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      continue;
    }
  }
  throw new Error("Chrome executable not found. Install Google Chrome or update CHROME_CANDIDATES.");
};

const parseViewport = (html) => {
  const match = html.match(/data-pencil-id="[^"]+"[\s\S]*?height:\s*(\d+)px;[\s\S]*?width:\s*(\d+)px/);
  if (!match) {
    return { width: 1080, height: 1440 };
  }
  return {
    height: Number(match[1]),
    width: Number(match[2])
  };
};

const buildWrapperHtml = (originalHtml, selector, viewport) => {
  const targetHtml = originalHtml.replace(
    "</head>",
    `
    <style>
      html, body {
        background: transparent !important;
        overflow: hidden !important;
        width: ${viewport.width}px;
        height: ${viewport.height}px;
      }
      body {
        display: flex;
        align-items: flex-start;
        justify-content: flex-start;
      }
      body > * {
        margin: 0 !important;
      }
      [data-pencil-id] {
        transform: none !important;
      }
    </style>
    </head>`
  );

  return targetHtml.replace(
    "</body>",
    `
    <script>
      (() => {
        const target = document.querySelector(${JSON.stringify(selector)});
        if (!target) {
          document.body.innerHTML = "<pre>Target selector not found: ${selector}</pre>";
          return;
        }
        document.body.innerHTML = "";
        document.body.appendChild(target);
      })();
    </script>
    </body>`
  );
};

const runChromeScreenshot = ({ chromePath, htmlPath, outputPath, viewport, scale }) => new Promise((resolve, reject) => {
  const chromeArgs = [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    `--window-size=${viewport.width},${viewport.height}`,
    `--force-device-scale-factor=${scale}`,
    `--screenshot=${outputPath}`,
    `file://${htmlPath}`
  ];

  const child = spawn(chromePath, chromeArgs, {
    stdio: ["ignore", "pipe", "pipe"]
  });

  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });

  child.on("error", reject);
  child.on("close", (code) => {
    if (code === 0) {
      resolve();
      return;
    }
    reject(new Error(`Chrome screenshot failed with code ${code}: ${stderr}`));
  });
});

const main = async () => {
  const options = parseArgs(process.argv);
  const chromePath = await resolveChromePath();
  const inputPath = path.resolve(ROOT, options.input);
  const outputPath = path.resolve(ROOT, options.output || path.join(DEFAULT_OUTPUT_DIR, `${path.basename(inputPath, ".html")}.png`));
  const html = await readFile(inputPath, "utf8");
  const viewport = parseViewport(html);
  const wrappedHtml = buildWrapperHtml(html, options.selector, viewport);

  await mkdir(path.dirname(outputPath), { recursive: true });

  const tempDir = path.join(os.tmpdir(), "pencil-html-render");
  await mkdir(tempDir, { recursive: true });
  const tempHtmlPath = path.join(tempDir, `${path.basename(inputPath, ".html")}.render.html`);

  const assetDir = path.dirname(inputPath);
  const normalizedHtml = wrappedHtml.replaceAll("url('./", `url('file://${assetDir}/`);

  await writeFile(tempHtmlPath, normalizedHtml, "utf8");

  await runChromeScreenshot({
    chromePath,
    htmlPath: tempHtmlPath,
    outputPath,
    viewport,
    scale: options.scale || "2"
  });

  console.log(`png=${path.relative(ROOT, outputPath)}`);
  console.log(`html=${path.relative(ROOT, inputPath)}`);
  console.log(`viewport=${viewport.width}x${viewport.height}`);
};

await main();
