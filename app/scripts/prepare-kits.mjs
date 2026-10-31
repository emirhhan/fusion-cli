// Fusion Kits paketini ve Node çalışma zamanını uygulama kaynaklarına hazırlar.
// Kits ayrı bir depodur (varsayılan: bu deponun yanındaki `fusion-kits`). Paket
// BELİRLEYİCİDİR: ana kopyanın çalışma ağacı (kaydedilmemiş değişiklikler, bayat
// `dist/`) değil, deponun SON COMMIT'i geçici bir git worktree'sinde derlenip
// paketlenir. Kits olmadan masaüstü paketi üretilmez; her hata açıkça durdurur.
import {
  chmodSync,
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import process from "node:process";
import { runtimeError } from "./check-runtime.mjs";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const kitsRoot = resolve(process.env.FUSION_KITS_DIR ?? resolve(appRoot, "../../fusion-kits"));
const target = resolve(appRoot, "src-tauri/resources/kits");
const node = process.env.FUSION_KITS_NODE ?? process.execPath;
const isWindows = process.platform === "win32";
const nodeName = isWindows ? "node.exe" : "node";
const DEPENDENCY_FILES = ["package.json", "package-lock.json"];

function fail(message, hint) {
  console.error(message);
  if (hint) console.error(hint);
  process.exit(1);
}

function git(args, cwd = kitsRoot) {
  return spawnSync("git", args, { cwd, encoding: "utf8" });
}

function checkNode() {
  const selected = spawnSync(node, ["--version"], { encoding: "utf8" });
  const version = (selected.stdout ?? "").trim();
  const issue = runtimeError("kits", version.replace(/^v/, ""));
  if (selected.status !== 0 || issue) {
    fail(issue ?? "Seçilen Kits Node ikilisi çalıştırılamadı.", "FUSION_KITS_NODE ile geçerli Node 24+ ikilisini gösterin.");
  }
  return version;
}

// Mach-O sihirli sayıları (32/64 bit, iki bayt sırası, evrensel ikili).
const MACH_O_MAGIC = new Set(["feedface", "feedfacf", "cefaedfe", "cffaedfe", "cafebabe", "bebafeca"]);
const SYSTEM_LIBRARY = /^(\/usr\/lib\/|\/System\/)/;

// Ölçüldü (31 Ekim): Homebrew `node` @rpath/libnode ve /opt/homebrew kitaplıklarına
// bağlı; pakete kopyalanınca Homebrew'suz Mac'te Kits hiç açılmaz. Paketlenen Node
// yalnız sistem kitaplıklarına bağlı (resmî nodejs.org) ikili olmalı.
function checkPortable() {
  if (process.platform !== "darwin") return;
  const magic = readFileSync(node).subarray(0, 4).toString("hex");
  if (!MACH_O_MAGIC.has(magic)) return;
  const linked = spawnSync("otool", ["-L", node], { encoding: "utf8" });
  if (linked.status !== 0) fail(`Kits Node ikilisinin bağımlılıkları okunamadı: ${node}`);
  const foreign = linked.stdout
    .split("\n")
    .slice(1)
    .map((line) => line.trim().split(" (")[0])
    .filter((library) => library && !SYSTEM_LIBRARY.test(library));
  if (foreign.length > 0) {
    fail(
      `Kits Node ikilisi taşınabilir değil (${node}); ${foreign.length} sistem dışı kitaplığa bağlı, ör.:\n  ${foreign.slice(0, 3).join("\n  ")}`,
      "Resmî Node ikilisini gösterin: FUSION_KITS_NODE=\"$(npx --yes --package=node@24.21.0 -- node -p process.execPath)\"",
    );
  }
}

function checkRepository() {
  if (!existsSync(kitsRoot)) {
    fail(`Fusion Kits deposu bulunamadı: ${kitsRoot}`, "FUSION_KITS_DIR ile Kits deposunu gösterin; Kits'siz paket üretilmez.");
  }
  const top = git(["rev-parse", "--show-toplevel"]);
  if (top.status !== 0 || realpathSync(top.stdout.trim()) !== realpathSync(kitsRoot)) {
    fail(`Fusion Kits dizini bir git deposu değil: ${kitsRoot}`, "Kits son commit'ten paketlenir; depo kökünü gösterin.");
  }
  const head = git(["rev-parse", "HEAD"]);
  if (head.status !== 0) fail(`Fusion Kits deposunda commit yok: ${kitsRoot}`);
  if (!existsSync(resolve(kitsRoot, "node_modules"))) {
    fail(`Fusion Kits bağımlılıkları kurulu değil: ${resolve(kitsRoot, "node_modules")}`, "Kits deposunda `npm ci` çalıştırın.");
  }
  // Geçici ağaç ana kopyanın node_modules'ünü kullanır; bağımlılık tanımı HEAD'den
  // sapmışsa derlenen paket commit'le eşleşmez.
  const drift = git(["diff", "--quiet", "HEAD", "--", ...DEPENDENCY_FILES]);
  if (drift.status !== 0) {
    fail(
      `Fusion Kits bağımlılık dosyalarında kaydedilmemiş değişiklik var (${DEPENDENCY_FILES.join(", ")}).`,
      "Değişikliği commit'leyin ya da geri alın; paket son commit'le birebir olmalı.",
    );
  }
  const dirty = git(["status", "--porcelain", "--untracked-files=no"]);
  return {
    commit: head.stdout.trim(),
    commitDate: git(["show", "-s", "--format=%cI", "HEAD"]).stdout.trim(),
    sourceDirty: dirty.stdout.trim() !== "",
  };
}

function run(command, args, cwd, failure) {
  const env = { ...process.env, PATH: `${dirname(node)}${delimiter}${process.env.PATH ?? ""}` };
  const result = spawnSync(command, args, { cwd, env, stdio: "inherit", shell: isWindows && command === "npm" });
  if (result.status !== 0) throw new Error(`${failure} (çıkış kodu ${result.status ?? result.signal ?? "?"})`);
}

function moveInto(source, destination) {
  rmSync(destination, { recursive: true, force: true });
  mkdirSync(dirname(destination), { recursive: true });
  try {
    renameSync(source, destination);
  } catch (error) {
    if (error?.code !== "EXDEV") throw error;
    cpSync(source, destination, { recursive: true, verbatimSymlinks: true });
    rmSync(source, { recursive: true, force: true });
  }
}

function packageFromHead(source, nodeVersion) {
  const workspace = mkdtempSync(resolve(tmpdir(), "fusion-kits-head-"));
  const tree = resolve(workspace, "kits");
  const staging = resolve(workspace, "kaynak");
  const modules = resolve(tree, "node_modules");
  let added = false;
  try {
    const add = git(["worktree", "add", "--detach", tree, source.commit]);
    if (add.status !== 0) throw new Error(`Geçici Kits ağacı açılamadı: ${add.stderr.trim()}`);
    added = true;
    symlinkSync(resolve(kitsRoot, "node_modules"), modules, isWindows ? "junction" : "dir");
    if (!existsSync(resolve(tree, "scripts/kits-bundle.mjs"))) {
      throw new Error(`Kits son commit'inde scripts/kits-bundle.mjs yok (${source.commit}).`);
    }
    // Bayat istemci pakete girmesin: istemci temiz ağaçta yeniden derlenir.
    run("npm", ["run", "build"], tree, "Kits istemcisi derlenemedi");
    run(node, [resolve(tree, "scripts/kits-bundle.mjs"), resolve(staging, "app")], tree, "Kits paketlenemedi");
    copyFileSync(node, resolve(staging, nodeName));
    chmodSync(resolve(staging, nodeName), 0o755);
    const manifest = {
      schema: 1,
      source: "HEAD",
      commit: source.commit,
      commitDate: source.commitDate,
      sourceDirty: source.sourceDirty,
      packagedAt: new Date().toISOString(),
      nodeVersion,
      platform: `${process.platform}-${process.arch}`,
    };
    writeFileSync(resolve(staging, "kits-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
    moveInto(staging, target);
    return manifest;
  } finally {
    if (existsSync(modules)) unlinkSync(modules);
    // Yalnız bu betiğin açtığı geçici ağaç kaldırılır; başka worktree'lere dokunulmaz.
    if (added) {
      const removed = git(["worktree", "remove", "--force", tree]);
      if (removed.status !== 0) console.error(`Geçici Kits ağacı kaldırılamadı: ${tree}\n${removed.stderr.trim()}`);
    }
    rmSync(workspace, { recursive: true, force: true });
  }
}

const nodeVersion = checkNode();
checkPortable();
const source = checkRepository();
let manifest;
try {
  manifest = packageFromHead(source, nodeVersion);
} catch (error) {
  fail(error instanceof Error ? error.message : String(error), "Kits'siz masaüstü paketi üretilmez; hatayı giderip yeniden çalıştırın.");
}
console.log(`Kits kaynakları hazır: ${target}`);
console.log(`Kits commit ${manifest.commit} (${manifest.commitDate}) · Node ${manifest.nodeVersion}`);
if (manifest.sourceDirty) {
  console.log("Not: Kits ana kopyasında kaydedilmemiş değişiklik var; pakete girmedi (paket son commit'ten).");
}
