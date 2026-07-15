import { spawn } from "node:child_process";
import path from "node:path";

const root = process.cwd();
const script = path.join(root, "09_tools", "new-day.py");
const child = spawn(process.env.PYTHON_BIN ?? "python3", [script, ...process.argv.slice(2)], {
  cwd: root,
  stdio: "inherit"
});

child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});

child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
