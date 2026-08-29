/**
 * Olay yükünü kullanıcıya gösterilecek tek satıra çevirir.
 *
 * Ham JSON asla gösterilmez: kullanıcı ne olduğunu okumak ister, veri yapısını
 * değil. Karşılığı olmayan olaylar `null` döner ve akışta hiç görünmez.
 */
export function olayMetni(veri: Record<string, unknown>): string | null {
  const olay = String(veri.olay ?? "");
  const ad = typeof veri.name === "string" ? veri.name : "";
  switch (olay) {
    case "ToolExecuted":
      return `araç çalıştı: ${ad}`;
    case "ModelCallStarted":
      return "model düşünüyor…";
    case "CapabilityActivated":
      return `${String(veri.name ?? "uzmanlık")} [${String(veri.source ?? "fusion")}] bu görev için otomatik seçildi`;
    case "FilesChanged": {
      const paths = veri.paths;
      if (!Array.isArray(paths) || !paths.every((path) => typeof path === "string")) return null;
      return `dosyalar değişti: ${paths.join(", ")}`;
    }
    case "TurnOutcome": {
      const durum = String(veri.status ?? "");
      if (durum === "completed") return "görev tamamlandı";
      if (durum === "partial") return "görev kısmi kaldı";
      return "görev başarısız";
    }
    default:
      return null;
  }
}
