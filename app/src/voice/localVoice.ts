import catalog from "../../../src/fusion_cli/appserver/data/voice-intents.json";
export function normalizeVoiceWords(text: string): string {
  return text.toLocaleLowerCase("tr-TR").replace(/ı/g, "i").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
}
const aliases = new Set(catalog.aliases.map(normalizeVoiceWords));
const replies = new Map(catalog.intents.flatMap(intent => intent.phrases.map(phrase => [normalizeVoiceWords(phrase), intent.reply] as const)));
export function localVoiceReply(text: string): string | null {
  const words = normalizeVoiceWords(text).split(" ");
  if (aliases.has(words[0])) words.shift();
  if (aliases.has(words[words.length - 1])) words.pop();
  return replies.get(words.join(" ")) ?? null;
}
