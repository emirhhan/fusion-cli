import type { Mesaj } from "../screens/Conversation";
import { olayEkle } from "../protocol/olayAkisi";

/** Yeniden açılan sohbet, canlı akışla aynı araç satırı sözleşmesini kullanır. */
export function historyMessages(rows: unknown[]): Mesaj[] {
  let messages: Mesaj[] = [];
  rows.forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const row = item as Record<string, unknown>;
    if (row.rol === "olay") {
      if (!row.olay || typeof row.olay !== "object" || Array.isArray(row.olay)) return;
      const event = row.olay as Record<string, unknown>;
      if (event.olay !== "ToolExecuted" || typeof event.name !== "string"
        || !["ok", "failed", "unknown", "denied", "blocked"].includes(String(event.outcome))) return;
      messages = olayEkle(messages, event);
      const last = messages[messages.length - 1];
      if (last && !last.id) messages[messages.length - 1] = { ...last, id: typeof row.id === "string" ? row.id : `history-${index}` };
      return;
    }
    if ((row.rol !== "kullanici" && row.rol !== "asistan") || typeof row.metin !== "string" || !row.metin.trim()) return;
    messages.push({ rol: row.rol, metin: row.metin,
      ...(row.ara === true && row.rol === "asistan" ? { ara: true } : {}),
      id: typeof row.id === "string" ? row.id : `history-${index}`,
    });
  });
  // Eski günlüklerde araçların gerçek zaman damgası yoktur; decoderın canlı
  // araç çözücüsünden aldığı açılış anını çalışma süresi gibi göstermeyelim.
  return messages.map(({ baslangicZamani: _start, bitisZamani: _end, ...message }) => message);
}
