import type { OlayAdimi } from "../protocol/olayMetni";
import type { Mesaj } from "../screens/Conversation";
import type { SessionModel } from "./types";

/** The turn ended, but no tool result arrived: its effect is unknown, not successful. */
export function closeUnfinishedTools(session: SessionModel): Mesaj[] {
  if (!session.running) return session.messages;
  const messages = session.messages;
  let boundary = messages.findIndex(message => message.rol === "kullanici" && message.id === `${session.requestId}:user`);
  if (boundary < 0) messages.forEach((message, index) => { if (message.rol === "kullanici") boundary = index; });
  const nextUser = messages.findIndex((message, index) => index > boundary && message.rol === "kullanici");
  const owned = (step: OlayAdimi, index: number): boolean => {
    if (!step.arac || !step.basladi || step.durum) return false;
    if (step.sessionId && step.sessionId !== session.id) return false;
    if (step.turnId && step.turnId !== session.turnId) return false;
    if (step.attemptId && step.attemptId !== session.turnId) return false;
    // Identified calls remain owned even if the user has already queued another message.
    if (step.turnId || step.attemptId) return true;
    return index > boundary && (nextUser < 0 || index < nextUser);
  };
  const finishedAt = Date.now();
  return messages.map((message, index) => {
    if (message.rol !== "olay" || !message.adimlar?.some(step => owned(step, index))) return message;
    const adimlar = message.adimlar.map(step => owned(step, index) ? {
      ...step, basladi: false, durum: "unknown", sonucAlinamadi: true,
      cikti: [step.cikti, "Tur sona erdi; bu aracın sonucu alınamadı."].filter(Boolean).join("\n"),
    } : step);
    return { ...message, adimlar,
      ...(message.baslangicZamani !== undefined && message.bitisZamani === undefined && !adimlar.some(step => step.basladi)
        ? { bitisZamani: finishedAt } : {}),
    };
  });
}
