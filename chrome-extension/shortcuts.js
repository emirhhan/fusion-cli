// Fusion Browser kısayolları (P-073): kullanıcının adla kaydettiği görevler; panelde "/ad"
// ile, ajanda `chrome_action shortcut=ad` ile çağrılır. Saf mantık: Chrome API'si yok.

/** Kısayol adı: boşluksuz harf/rakam/_/-, en çok 40 karakter (paneldeki kayıt kuralıyla aynı). */
export const SHORTCUT_NAME = /^[\p{L}\p{N}_-]{1,40}$/u;

/** Adı (Türkçe büyük/küçük harf duyarsız) eşleşen kısayol ya da null. */
export function findShortcut(shortcuts, name) {
  const wanted = String(name || "").trim().toLocaleLowerCase("tr");
  return shortcuts.find((item) => String(item.ad).toLocaleLowerCase("tr") === wanted) || null;
}

/**
 * `/ad kalan metin` → `{ prompt, shortcut, unknown }`: kayıtlı görev (+ kalan metin).
 *
 * Kısayol yoksa metin OLDUĞU GİBİ döner: "/Users/x/app.js dosyasını açıkla", "/etc/hosts",
 * "/ bu sayfayı özetle" kısayol değildir. Ölçüldü (31 Ekim, bağımsız inceleme): "/" ile
 * başlayan her mesaj kısayol sanılıyor, eşleşme yokken hata atılıp mesaj gönderilmiyordu.
 * `unknown` yalnız mesajın tamamı "/ad" biçimindeyse ve en az bir kayıtlı kısayol varken
 * dolar (yazım hatası olabilir; panel listeyi gösterip sorar).
 */
export function expandShortcut(prompt, shortcuts) {
  const none = { prompt, shortcut: null, unknown: null };
  const match = /^\/(\S+)(?:\s+([\s\S]*))?$/.exec(prompt);
  if (!match || !SHORTCUT_NAME.test(match[1])) return none;
  const [, name, rest = ""] = match;
  const hit = findShortcut(shortcuts, name);
  if (!hit) return rest.trim() || !shortcuts.length ? none : { ...none, unknown: name };
  const tail = rest.trim();
  return { prompt: tail ? `${hit.metin}\n${tail}` : hit.metin, shortcut: hit.ad, unknown: null };
}
