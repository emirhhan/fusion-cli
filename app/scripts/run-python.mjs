import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// Yol `fileURLToPath` ile çözülür: `URL.pathname` Windows'ta "/C:/..." üretir ve
// spawn bunu çalıştıramaz.
const isWindows = process.platform === "win32";
const venvPython = fileURLToPath(
  new URL(isWindows ? "../../.venv/Scripts/python.exe" : "../../.venv/bin/python", import.meta.url),
);
// Sistem yorumlayıcısının adı da platforma göre değişir: Windows'ta `python3`
// çoğu zaman yalnızca Mağaza kısayoludur ve gerçek yorumlayıcıyı çalıştırmaz.
const systemPython = isWindows ? "python" : "python3";

const python = process.env.FUSION_BUILD_PYTHON
  || (existsSync(venvPython) ? venvPython : systemPython);
const result = spawnSync(python, process.argv.slice(2), { stdio: "inherit" });

if (result.error) throw result.error;
process.exit(result.status ?? 1);
