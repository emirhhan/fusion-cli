/**
 * Sohbet başlığı üretimi.
 *
 * Claude'daki davranış: başlık konuşmanın ilk birkaç kelimesinden gelir, tüm
 * mesajın kesilmiş hâlinden değil. Kenar çubuğunda okunabilir olması için kısa
 * kalmalı; bunun için model çağırmak yavaş ve pahalıdır, saf metinle yapılır.
 */

/** Başlıkta gösterilecek en fazla kelime. */
const MAX_WORDS = 4;

/** Kelime sınırında kesilse bile aşılmaması gereken karakter tavanı. */
const MAX_CHARS = 48;

/** Henüz mesaj yazılmamış sekmenin adı. */
export const DEFAULT_TITLE = "Yeni görev";

/** Başlığa taşınmayacak kenar noktalaması. Cümle içi kesme işareti korunur. */
const EDGE_PUNCTUATION = /^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu;

/**
 * İlk mesajdan kısa bir başlık üret.
 *
 * Boş ya da yalnızca noktalama içeren girdi varsayılan başlığa düşer: sekmenin
 * adsız kalması, anlamsız bir başlıktan iyidir.
 */
export function titleFromTask(task: string): string {
  const words = task
    .replace(/\s+/gu, " ")
    .trim()
    .split(" ")
    .map((word) => word.replace(EDGE_PUNCTUATION, ""))
    .filter((word) => word.length > 0);
  if (words.length === 0) return DEFAULT_TITLE;

  const picked: string[] = [];
  for (const word of words.slice(0, MAX_WORDS)) {
    const candidate = [...picked, word].join(" ");
    // İlk kelime tavanı tek başına aşıyorsa yine de alınır; aksi halde başlık
    // boş kalır ve sekme adsız görünür.
    if (candidate.length > MAX_CHARS && picked.length > 0) break;
    picked.push(word);
  }
  return picked.join(" ").slice(0, MAX_CHARS);
}
