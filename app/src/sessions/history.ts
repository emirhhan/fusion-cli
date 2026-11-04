import type { Mesaj } from "../screens/Conversation";
import { olayEkle } from "../protocol/olayAkisi";
import { decodeReviewFindings } from "../protocol/reviewFindings";

/** Yeniden açılan sohbet, canlı akışla aynı araç satırı sözleşmesini kullanır. */
export function historyMessages(rows: unknown[], truncated = false): Mesaj[] {
  let limited = truncated;
  let redacted = false;
  let messages: Mesaj[] = [];
  rows.forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const row = item as Record<string, unknown>;
    if (row.rol === "olay") {
      if (!row.olay || typeof row.olay !== "object" || Array.isArray(row.olay)) return;
      const event = row.olay as Record<string, unknown>;
      if (event.olay !== "ToolExecuted" || typeof event.name !== "string"
        || !["ok", "failed", "unknown", "denied", "blocked"].includes(String(event.outcome))) return;
      limited ||= Array.isArray(event.history_truncated) && event.history_truncated.length > 0;
      redacted ||= Array.isArray(event.history_redacted) && event.history_redacted.length > 0;
      messages = olayEkle(messages, event);
      const last = messages[messages.length - 1];
      if (last && !last.id) messages[messages.length - 1] = { ...last, id: typeof row.id === "string" ? row.id : `history-${index}` };
      return;
    }
    if ((row.rol !== "kullanici" && row.rol !== "asistan") || typeof row.metin !== "string") return;
    // `/code-review` bulguları (#214) canlı turdaki gibi kart olur; metni boş olabilir.
    const findings = row.rol === "asistan" ? decodeReviewFindings(row.bulgular) : undefined;
    if (!row.metin.trim() && !findings) return;
    messages.push({ rol: row.rol, metin: row.metin,
      ...(row.ara === true && row.rol === "asistan" ? { ara: true } : {}),
      ...(findings ? { findings } : {}),
      id: typeof row.id === "string" ? row.id : `history-${index}`,
    });
  });
  if (limited || redacted) {
    const text = [
      limited ? "Geçmiş boyut sınırları nedeniyle kısaltıldı; bazı mesajlar, adımlar veya ayrıntılar gösterilmiyor." : "",
      redacted ? "Bazı araç ayrıntıları hassas bilgi içerdiği için gizlendi." : "",
    ].filter(Boolean).join(" ");
    messages.unshift({ rol: "bildirim", id: "history-notice", metin: text });
  }
  // Eski günlüklerde araçların gerçek zaman damgası yoktur; decoderın canlı
  // araç çözücüsünden aldığı açılış anını çalışma süresi gibi göstermeyelim.
  return messages.map(({ baslangicZamani: _start, bitisZamani: _end, ...message }) => message);
}
