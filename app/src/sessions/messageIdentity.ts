import type { Mesaj } from "../screens/Conversation";

/** Eski döküm kimliği içerik ve aynı içeriğin occurrence'ına bağlanır. */
export function migrateMessageIds(messages: Mesaj[], namespace: string): Mesaj[] {
  const occurrences = new Map<string, number>();
  return messages.map((message) => {
    const content = JSON.stringify([message.rol, message.metin, message.ekler ?? []]);
    const occurrence = occurrences.get(content) ?? 0;
    occurrences.set(content, occurrence + 1);
    if (message.id) return message;
    return { ...message, id: `legacy:${namespace}:${encodeURIComponent(content)}:${occurrence}` };
  });
}
