import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

/**
 * Bildirim kartı bir süre gözlem panelinin (`.app-shell__inspector`)
 * ALTINDA kalıp görünmüyordu: ikisi de sabit z-index kullanıyordu ama
 * panel (`--z-overlay` + 1 = 31) bildirimden (`--z-overlay` = 30) daha
 * yüksekti. jsdom gerçek katmanlama hesaplamadığı için burada CSS
 * dosyalarının METNİ okunup regresyona karşı korunuyor — Playwright
 * görsel testi ayrıca `app/e2e` altında koşulabilir.
 */
const kokDizin = dirname(fileURLToPath(import.meta.url));

function dosyaOku(goreliYol: string): string {
  return readFileSync(join(kokDizin, goreliYol), "utf-8");
}

describe("bildirim katman sırası", () => {
  test("bildirim --z-toast kullanır, --z-overlay/--z-dialog değil", () => {
    const css = dosyaOku("notification.css");
    expect(css).toMatch(/\.notification\s*{[^}]*z-index:\s*var\(--z-toast\)/s);
  });

  test("--z-toast, kod tabanındaki bilinen en yüksek sabit z-index'ten büyük", () => {
    const tokens = dosyaOku("../theme/tokens.css");
    const eslesme = tokens.match(/--z-toast:\s*(\d+)/);
    expect(eslesme).not.toBeNull();
    const zToast = Number(eslesme?.[1]);

    // Bağlayıcı diyaloğu (ConnectorsScreen.css) 1000 gibi yüksek, tema
    // dizgesine bağlı olmayan sabit bir değer kullanıyor; toast'ın onu da
    // aşması gerekiyor.
    expect(zToast).toBeGreaterThan(1000);
  });

  test("gözlem paneli (.app-shell__inspector) --z-overlay tabanlı kalır, toast'ı geçemez", () => {
    const shellCss = dosyaOku("../screens/Shell.css");
    expect(shellCss).toMatch(/\.app-shell__inspector\s*{[^}]*z-index:\s*calc\(var\(--z-overlay\)\s*\+\s*1\)/s);
  });
});
