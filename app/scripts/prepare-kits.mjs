// Fusion Kits paketini ve Node çalışma zamanını uygulama kaynaklarına hazırlar.
// Kits ayrı bir depodur (varsayılan: bu deponun yanındaki `fusion-kits`); yoksa
// uygulama Kits'siz paketlenir ve bölüm kurulum mesajı gösterir.
import { chmodSync, copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import process from "node:process";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const kitsRoot = resolve(process.env.FUSION_KITS_DIR ?? resolve(appRoot, "../../fusion-kits"));
const target = resolve(appRoot, "src-tauri/resources/kits");
const node = process.env.FUSION_KITS_NODE ?? process.execPath;

if (Number(process.versions.node.split(".")[0]) < 24 && !process.env.FUSION_KITS_NODE) {
  console.error("Kits paketi Node 24+ ister. FUSION_KITS_NODE ile Node 24 ikilisini gösterin.");
  process.exit(1);
}
if (!existsSync(resolve(kitsRoot, "scripts/kits-bundle.mjs"))) {
  console.error(`Fusion Kits deposu bulunamadı: ${kitsRoot}`);
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
const bundled = spawnSync(node, [resolve(kitsRoot, "scripts/kits-bundle.mjs"), resolve(target, "app")], {
  cwd: kitsRoot,
  stdio: "inherit",
});
if (bundled.status !== 0) process.exit(bundled.status ?? 1);
const nodeName = process.platform === "win32" ? "node.exe" : "node";
copyFileSync(node, resolve(target, nodeName));
chmodSync(resolve(target, nodeName), 0o755);
console.log(`Kits kaynakları hazır: ${target}`);
