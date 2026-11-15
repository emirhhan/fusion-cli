import type { ComposerAttachment } from "./screens/Composer";

/**
 * Gönderilen metin yol gibi mi başlıyor? ("/Users/ben/app.py neden çöküyor?")
 *
 * Ölçüldü (29 Ekim, U3-25): `/` ile başlayan HER metin komut sayılıyor, mutlak yolla başlayan normal
 * istem çekirdeğe "bilinmeyen komut" olarak gidiyor ve model hiç çalışmıyordu. İlk sözcükte `/` ya da
 * `\` ayracı veya dosya uzantısı varsa bu bir komut değil görevdir; tek sözcüklü yazım hataları
 * (`/foo`) hâlâ komut hatası alır.
 */
export function startsWithFilePath(task: string): boolean {
  const first = task.trimStart().split(/\s+/u, 1)[0] ?? "";
  if (!first.startsWith("/") || first.length < 2) return false;
  return /[\\/.]/u.test(first.slice(1));
}

/** `/klasor` komutu argümanlı da yazılabilir (`/klasor ~/proje`); ilk sözcük ad ise klasör komutudur (U3-34). */
export function isFolderCommand(task: string, ad: string): boolean {
  return (task.trim().split(/\s+/u, 1)[0] ?? "").toLocaleLowerCase("tr") === `/${ad}`;
}

const ABSOLUTE_PATH = /^(?:\/|[A-Za-z]:[\\/]|\\\\)/u;

/**
 * DOM bırakma yolundan gelen dosyaları ekletir. Yerel mutlak yol (`file.path`, Tauri/Electron'a özgü)
 * çözülemiyorsa çıplak dosya adı "yol" diye EKLENMEZ: çekirdek onu göreli sayıp bulamaz ya da yanlış
 * dosyaya bağlardı (U3-26). Aynı yol bir kez eklenir.
 */
export function attachmentsFromDroppedFiles(
  files: readonly File[], mevcut: readonly ComposerAttachment[] = [],
): { additions: ComposerAttachment[]; unresolved: number } {
  const additions: ComposerAttachment[] = [];
  let unresolved = 0;
  for (const file of files) {
    const path = (file as File & { path?: string }).path ?? "";
    if (!ABSOLUTE_PATH.test(path.trim())) { unresolved += 1; continue; }
    if (mevcut.some((item) => item.path === path) || additions.some((item) => item.path === path)) continue;
    additions.push({ kind: file.type.startsWith("image/") ? "image" : "file", name: file.name, path });
  }
  return { additions, unresolved };
}
