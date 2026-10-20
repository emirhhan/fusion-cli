/** Canonical marka kaynağından App ve bağımsız Kits için aynı CSS snapshot'u. */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

export function brandCss(source) {
  if (source?.schemaVersion !== 1) throw new Error("Marka token şeması desteklenmiyor.");
  const declarations = (values) => {
    if (!values || typeof values !== "object" || Array.isArray(values)) throw new Error("Token grubu geçersiz.");
    return Object.entries(values).sort(([a], [b]) => a.localeCompare(b, "en")).map(([name, value]) => {
      if (!/^[a-z][a-z0-9-]*$/.test(name) || !/^#[0-9a-f]{6}$/i.test(value)) throw new Error("Token adı veya renk geçersiz.");
      return `  --fusion-${name}: ${value.toLowerCase()};`;
    }).join("\n");
  };
  return `/* ÜRETİLMİŞ — kaynak: Fusion app/src/theme/brand-tokens.json */\n:root {\n${declarations(source.palette)}\n${declarations(source.light)}\n}\n:root[data-theme="dark"] {\n${declarations(source.dark)}\n}\n`;
}

export function generate({ check = false, appOnly = false } = {}) {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const source = readFileSync(resolve(root, "app/src/theme/brand-tokens.json"), "utf8");
  const css = brandCss(JSON.parse(source));
  const kits = resolve(root, "../fusion-kits");
  const outputs = [resolve(root, "app/src/theme/brand.generated.css")];
  if (!appOnly) outputs.push(resolve(kits, "src/client/fusion-brand.generated.css"));
  for (const path of outputs) {
    if (check) {
      if (readFileSync(path, "utf8").replace(/\r\n/g, "\n") !== css) throw new Error("Üretilmiş marka token'ları güncel değil.");
    } else writeFileSync(path, css);
  }
  if (appOnly) return;
  const receipt = JSON.stringify({ schemaVersion: 1, sourceSha256: createHash("sha256").update(source).digest("hex"), cssSha256: createHash("sha256").update(css).digest("hex") }, null, 2) + "\n";
  const receiptPath = resolve(kits, "src/shared/fusion-brand-manifest.json");
  if (check) {
    if (readFileSync(receiptPath, "utf8") !== receipt) throw new Error("Marka token makbuzu güncel değil.");
  } else writeFileSync(receiptPath, receipt);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) generate({ check: process.argv.includes("--check"), appOnly: process.argv.includes("--app-only") });
