/** Model cevabını seslendirilecek düz metne çevirir. Markdown işaretleri,
 * kod blokları ve bağlantı adresleri okunmaz; çok uzun cevap kırpılır (tamamı
 * sohbette yazılı durur). */
export const SPOKEN_TEXT_LIMIT = 1_200;

export function spokenText(markdown: string, limit = SPOKEN_TEXT_LIMIT) {
  const text = markdown
    .replace(/```[\s\S]*?```/g, ' Kod bloğu sohbette. ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, 'bağlantı')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/\|/g, ' ')
    .replace(/(\*\*|__|\*|_|~~)(\S[\s\S]*?\S|\S)\1/g, '$2')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '')
    .replace(/\s*\n+\s*/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const end = Math.max(
    cut.lastIndexOf('. '),
    cut.lastIndexOf('? '),
    cut.lastIndexOf('! '),
  );
  return `${end > limit / 2 ? cut.slice(0, end + 1) : cut} Devamı sohbette yazılı.`;
}

/** Cümlelere böler: ilk cümle, cevabın tamamı hazırlanmadan seslendirilebilir. */
export function splitSentences(text: string): string[] {
  return (text.match(/[^.!?…]+(?:[.!?…]+|$)/g) ?? [])
    .map((part) => part.trim())
    .filter(Boolean);
}
