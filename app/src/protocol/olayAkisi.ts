import type { GorevMaddesi, Mesaj, TakipOnerisi } from "../screens/Conversation";
import { olayAdimi, type OlayAdimi } from "./olayMetni";

/**
 * Olayı sohbet akışına ekle.
 *
 * Ardışık adımlar TEK bir çalışma bloğunda toplanır. Eskiden her olay ayrı bir
 * satır açıyordu ve iki model çağrısı üst üste iki özdeş "model düşünüyor…"
 * satırı olarak görünüyordu — kullanıcı bunu tekrar sandı, haklıydı.
 *
 * Turun sonucu ("görev tamamlandı") bloğa KATILMAZ: o bir adım değil, akışın
 * kapanışıdır ve kendi satırında durur.
 */
export function olayEkle(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] {
  const akanSonuc = akanCevap(messages, event);
  if (akanSonuc) return akanSonuc;

  const gorevSonuc = gorevListesi(messages, event);
  if (gorevSonuc) return gorevSonuc;

  const oneriSonuc = takipOnerileri(messages, event);
  if (oneriSonuc) return oneriSonuc;

  const adim = olayAdimi(event);
  if (!adim) return messages;

  if (adim.sonuc) {
    return [...messages, { rol: "olay", metin: adim.metin, adimlar: [adim] }];
  }

  const son = messages[messages.length - 1];
  const bloklanabilir = son?.rol === "olay" && !son.adimlar?.some((item) => item.sonuc);
  if (!bloklanabilir) {
    const acilan: Mesaj[] = [...messages, { rol: "olay", metin: adim.metin, adimlar: [adim] }];
    return adim.diff ? [...acilan, degisiklikMesaji(adim)] : acilan;
  }

  const adimlar = [...(son.adimlar ?? []), adim];
  const guncel: Mesaj[] = [...messages.slice(0, -1), { ...son, adimlar, metin: adim.metin }];
  return adim.diff ? [...guncel, degisiklikMesaji(adim)] : guncel;
}

/** Araç çıktısındaki işaretlerin durum karşılığı. */
const GOREV_DURUMU: Record<string, GorevMaddesi["durum"]> = {
  "☐": "bekliyor",
  "▶": "yapiliyor",
  "☒": "bitti",
};

/**
 * Modelin görev listesini canlı kart olarak göster.
 *
 * `todo_write` aracı çalışıyordu ama çıktısı akışta sıradan bir "araç çalıştı"
 * satırıydı: kullanıcı planın neresinde olunduğunu göremiyordu. Liste TEK kart
 * olarak durur ve her güncellemede yerine geçer; çoğalması planı okunmaz yapardı.
 */
function gorevListesi(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] | null {
  if (event.olay !== "ToolExecuted" || event.name !== "todo_write") return null;
  if (event.outcome !== undefined && event.outcome !== "ok") return null;
  const cikti = typeof event.output === "string" ? event.output : "";
  const gorevler: GorevMaddesi[] = [];
  for (const satir of cikti.split("\n")) {
    const kirpik = satir.trim();
    const durum = GOREV_DURUMU[kirpik.slice(0, 1)];
    if (!durum) continue;
    const metin = kirpik.slice(1).trim();
    if (metin) gorevler.push({ durum, metin });
  }
  if (gorevler.length === 0) return messages;
  const eskisiz = messages.filter((mesaj) => mesaj.rol !== "gorevler");
  return [...eskisiz, { rol: "gorevler", metin: "Görevler", gorevler }];
}

/**
 * Model yazarken metni canlı göster.
 *
 * Çekirdek `TokenReceived` olaylarını zaten gönderiyordu ama arayüz onları
 * yok sayıyordu: cevap ancak tur bitince, tek parça hâlinde düşüyordu. Claude'da
 * metin yazıldıkça görünür; ölçüldü (17 Eylül denetimi) — bekleyen kullanıcı
 * turun ilerleyip ilerlemediğini göremiyordu.
 *
 * Akan balon GEÇİCİDİR: tur bitince kalkar, nihai cevabı uygulama ekler. Böylece
 * motorun kabul etmediği ara metin kalıcı cevap gibi durmaz.
 */
function akanCevap(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] | null {
  const olay = String(event.olay ?? "");
  if (olay === "TokenReceived") {
    // Arka plan çağrıları (ders çıkarımı, özet) kullanıcının cevabı değildir.
    if (event.channel !== undefined && event.channel !== "main") return messages;
    const parca = typeof event.text === "string" ? event.text : "";
    if (!parca) return messages;
    const son = messages[messages.length - 1];
    if (son?.rol === "asistan" && son.akan) {
      const guncel: Mesaj = { ...son, metin: son.metin + parca };
      return [...messages.slice(0, -1), guncel];
    }
    return [...messages, { rol: "asistan", metin: parca, akan: true }];
  }
  if (olay === "ModelCallStarted" || olay === "TurnFinished" || olay === "TurnAnswered") {
    // Yeni çağrı yeni metin demektir; biten tur ise nihai cevaba yerini bırakır.
    const temiz = messages.filter((mesaj) => !(mesaj.rol === "asistan" && mesaj.akan));
    if (olay !== "ModelCallStarted") return temiz;
    return temiz.length === messages.length ? null : (olayEkle(temiz, event) as Mesaj[]);
  }
  return null;
}

/**
 * Değişiklik KALICI bir mesajdır, çalışma bloğunun parçası değil.
 *
 * Çalışma göstergesi iş bitince kaybolur; dosyaya ne yazıldığı kaybolmamalı.
 * Kullanıcının elinde kalan tek kanıt budur.
 */
function degisiklikMesaji(adim: OlayAdimi): Mesaj {
  return { rol: "degisiklik", metin: adim.yol ?? "", diff: adim.diff };
}


/**
 * Tur sonundaki takip önerilerini akışa ekle.
 *
 * Öneriler adım DEĞİLDİR: çalışma bloğuna katılmaz, turun kapanışının ardına
 * kendi satırında düşer. Boş liste hiç mesaj açmaz — kanıt yoksa öneri de yok
 * (bkz. `core/followups.py`).
 */
function takipOnerileri(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] | null {
  if (event.olay !== "FollowupsSuggested") return null;
  const ham = Array.isArray(event.items) ? event.items : [];
  const oneriler: TakipOnerisi[] = ham
    .filter((item): item is [string, string] =>
      Array.isArray(item) && typeof item[0] === "string" && typeof item[1] === "string",
    )
    .map(([etiket, gorev]) => ({ etiket, gorev }));
  if (oneriler.length === 0) return messages;
  return [...messages, { rol: "oneriler", metin: "", oneriler }];
}
