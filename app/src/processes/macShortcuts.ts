/**
 * macOS terminal kısayolları → kabuğa gidecek bayt dizisi.
 *
 * xterm.js ⌘ ile gelen tuşları kabuğa iletmez; Terminal.app ve iTerm'de
 * alışılan satır/kelime düzenleme kısayolları bu yüzden çalışmıyordu.
 * Dönüş: gönderilecek dizi, `"temizle"` (⌘K) ya da kısayol değilse `null`.
 * ⌘C/⌘V burada YOK: onları uygulamanın Düzen menüsü yerel kopyala/yapıştır
 * olayıyla zaten xterm'e iletir; ikinci kez işlemek çift yapıştırma olur.
 */
export type MacShortcut = string | "temizle" | null;

interface KeyLike {
  key: string;
  metaKey: boolean;
  altKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
}

export function macTerminalShortcut(event: KeyLike): MacShortcut {
  if (event.ctrlKey || event.shiftKey) return null;
  if (event.metaKey && !event.altKey) {
    if (event.key === "Backspace") return "\x15"; // satırın başına kadar sil (Ctrl+U)
    if (event.key === "ArrowLeft") return "\x01"; // satır başı (Ctrl+A)
    if (event.key === "ArrowRight") return "\x05"; // satır sonu (Ctrl+E)
    if (event.key.toLowerCase() === "k") return "temizle";
    return null;
  }
  if (event.altKey && !event.metaKey) {
    if (event.key === "Backspace") return "\x1b\x7f"; // önceki kelimeyi sil
    if (event.key === "ArrowLeft") return "\x1bb"; // bir kelime geri
    if (event.key === "ArrowRight") return "\x1bf"; // bir kelime ileri
  }
  return null;
}
