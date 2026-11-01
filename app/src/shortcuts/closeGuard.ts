/**
 * ⌘W (oturumu kapat, #444) çalışan turu korur.
 *
 * Claude Desktop tablosunda ⌘W oturumu kapatır. Pencere kapatma refleksiyle basılınca çalışan tur
 * yarım kalmasın diye: tur yoksa hemen kapatılır; tur çalışıyorsa ilk basış yalnız uyarır ve
 * süre içinde ikinci basış kapatır.
 */
export const CLOSE_CONFIRM_WINDOW_MS = 3000;

export function closeDecision(running: boolean, now: number, armedAt: number | null): "close" | "arm" {
  if (!running) return "close";
  return armedAt !== null && now - armedAt < CLOSE_CONFIRM_WINDOW_MS ? "close" : "arm";
}
