import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const localPython = new URL("../../.venv/bin/python", import.meta.url).pathname;
const python = process.env.FUSION_BUILD_PYTHON
  || (existsSync(localPython) ? localPython : "python3");
const result = spawnSync(python, process.argv.slice(2), { stdio: "inherit" });

if (result.error) throw result.error;
process.exit(result.status ?? 1);
