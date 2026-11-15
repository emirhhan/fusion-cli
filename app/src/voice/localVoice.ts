import { prepareTurkishSpeech } from "./speechPronunciation";
import catalog from "../../../src/fusion_cli/appserver/data/voice-intents.json";
export function normalizeVoiceWords(text: string): string {
  return text.toLocaleLowerCase("tr-TR").replace(/ı/g, "i").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
}
const aliases = new Set(catalog.aliases.map(normalizeVoiceWords));
const replies = new Map(catalog.intents.flatMap(intent => intent.phrases.map(phrase => [normalizeVoiceWords(phrase), intent.reply] as const)));
const waitingReplies = new Map([
  ["isler nasil gidiyor", "İlk sorunun cevabını bekliyorum. Senin işlerin nasıl gidiyor?"],
  ["bugun bayagi yogunum", "Kolay gelsin. Bugün seni en çok hangi iş uğraştırıyor?"],
  ["bugun cok yoruldum", "Uzun bir gün olmuş. Biraz anlatmak ister misin?"],
  ["ne yapiyorsun", "Fusion’dan haber bekliyorum. Bu arada seni dinliyorum."],
  ["napiyorsun", "Fusion’dan haber bekliyorum. Bu arada seni dinliyorum."],
]);
const listenerCues = new Set(["hmm", "hm", "hmmm", "hi hi", "he he", "mhm", "uhu"]);
export const isVoiceListenerCue = (text: string) => listenerCues.has(normalizeVoiceWords(text));
const talkReplies = new Map([
  ["kac yasindasin", "Benim bir yaşım yok. İstersen başka bir şey sorabilirsin."],
  ["kac yasindasin diyorum", "Benim bir yaşım yok."],
  ["ben de iyiyim", "İyi olmana sevindim."],
  ["iyiyim", "İyi olmana sevindim."],
  ["iyiyim sag ol", "İyi olmana sevindim."],
  ["ben de iyiyim merhabalar", "İyi olmana sevindim."],
  ["nasilsin 1 dakika dur", "İyiyim, teşekkürler. Tabii, bekliyorum."],
]);

export function formatVoiceDate(now: Date): string {
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "full" }).format(now);
}

export function localVoiceReply(text: string, pending = false): string | null {
  const words = normalizeVoiceWords(text).split(" ");
  if (aliases.has(words[0])) words.shift();
  if (aliases.has(words[words.length - 1])) words.pop();
  const phrase = words.join(" ")
    .replace(/ (?:fusion|fuzyon|fizyo|filizcan|kit|bugun|bakalim|sen)$/u, '')
    .replace(/^(?:(?:fusion|fuzyon|fizyo|filizcan|kit|merhaba|selam|bu arada|peki) )+/u, '');
  const calendarQuestion = phrase.replace(/^(?:su an|su anda|simdi|bugun) /u, "");
  if (/^(?:hangi yildayiz|hangi yilin icindeyiz|kacinci yildayiz|kac yilindayiz|(?:bu )?yil kac|yil ne)$/u.test(calendarQuestion)) {
    return `${new Date().getFullYear()} yılındayız.`;
  }
  if (/^(?:(?:bugunun )?tarih(?:i)? (?:ne|nedir)|ayin kaci|gunlerden ne|gunlerden hangi gun|hangi gundeyiz)$/u.test(calendarQuestion)) {
    return `Bugün ${formatVoiceDate(new Date())}.`;
  }
  if (/^(?:(?:sen|ya sen) )?(?:nasil sin|nasilsin|nasilsiniz|nasilsin sen|naber|ne haber|sen nasilsin)(?: bu arada)?$/u.test(phrase)) {
    return "İyiyim, teşekkür ederim. Sen nasılsın?";
  }
  return (pending ? waitingReplies.get(phrase) : undefined) ?? talkReplies.get(phrase) ?? replies.get(phrase) ?? null;
}

/** Araçlı tura yalnız doğrudan bir eylem isteği gider. */
export function isSpokenWorkRequest(text: string): boolean {
  const words = normalizeVoiceWords(text.replace(/“[^”]*”|"[^"]*"|‘[^’]*’|(^|\s)'[^']*'(?=\s|[.!?,]|$)/gu, " "));
  // Aktarılan ya da örnek olarak verilen bir komut, eylem isteği sayılmaz.
  if (/\b(?:internette|webde|resmi kaynaklardan|guncel kaynaklardan)\b.*\b(?:ara|arastir|bak|dogrula|kontrol et|bul)\b/u.test(words)) return false;
  if (/\b(?:desem|dersem|diyelim|demek)\b/u.test(words)
    || /\b(?:nasil|neden) (?:yaparim|yapilir|olur|silerim|calisir|calistiririm|ederim)\b/u.test(words)) return false;
  if (/\b(?:fusion a (?:gorev ver|ilet)|(?:bunu|isini|gorevi) (?:yap|baslat|bitir|tamamla)|(?:ise )?devam et)(?: lutfen)?$/u.test(words)) return true;
  const target = /\b(?:dosya\w*|klasor\w*|dizin\w*|proje\w*|kod\w*|test\w*|komut\w*|terminal\w*|repo\w*|takvim\w*|belge\w*|rapor\w*|e posta\w*|mesaj\w*|ekran\w*|uygulama\w*|tablo\w*|gorsel\w*|sunum\w*|taslak\w*|not\w*|liste\w*|slayt\w*|grafik\w*|pdf\w*|csv\w*|xlsx\w*|ozet\w*|kayit\w*)\b/u;
  const action = /\b(?:listele|ac|oku|goster|incele|analiz et|kontrol et|duzenle|duzelt|calistir|sil|olustur|yaz|gonder|kaydet|ara|arastir|bul|bak|ekle|tasi|indir|test et|hazirla|uret|tasarla|ozetle|donustur|karsilastir|disa aktar|cikar|planla|aktar|guncelle|tara)(?:(?:r|ir|er|ar|ur|yabilir|yebilir|ebilir|abilir) misin(?:iz)?)?(?: lutfen)?$/u;
  return target.test(words) && action.test(words);
}

// Kapanışı olmayan bir araç turunda, protokolün arkasındaki içerik de seslendirilmez.
const toolBlock = /(?<![/\p{L}\p{N}])<?\bfusion[_ ]?tool[_ ]?call\b\s*>?[\s\S]*?(?:<?\s*(?:\/\s*fusion[_ ]?tool[_ ]?call\b|fusion[_ ]?tool[_ ]?call[_ ]?end\b)\s*>?|$)/giu;
const toolEnd = /<?\s*(?:\/\s*fusion[_ ]?tool[_ ]?call\b|\bfusion[_ ]?tool[_ ]?call[_ ]?end\b)\s*>?/giu;
export function stripVoiceToolMarkup(text: string): string {
  return text.replace(toolBlock, " ").replace(toolEnd, " ");
}

export function voicePronunciation(text: string): string {
  return prepareTurkishSpeech(stripVoiceToolMarkup(text));
}

/** Tanıma varyantlarını yalnız isteğe giden metinde birleştirir. */
export function normalizeSpokenNames(text: string): string {
  return text.replace(/\bMoto[ -]?(?:Gate|Geyt)\b/giu, "MotoGate");
}

export const NO_SPOKEN_ANSWER = "Fusion’dan sesli aktarabileceğim bir cevap gelmedi.";

/** Konuşmada kullanıcıya ait cevabı alır. Tam çekirdek yanıtı sohbet kaydında tutulur. */
export function spokenTeacherAnswer(text: string, inChat = true): string {
  const cleaned = stripVoiceToolMarkup(text)
    .replace(/\x60\x60\x60[\s\S]*?\x60\x60\x60/gu, inChat ? " Kod sohbette. " : " ")
    .replace(/\[([^\]]+)\]\([^)]+\)/gu, "$1")
    .replace(/https?:\/\/\S+/gu, "bağlantı")
    .replace(/^\s*#{1,6}\s+/gmu, "").replace(/[*_\x60]/gu, "")
    .replace(/^\s*[-•]\s+/gmu, "")
    .replace(/^\s*[|:\s-]+$/gmu, "");
  const sentences = cleaned.split(/(?<=[.!?])\s+|\n+/u).map(line => line.trim()).filter(Boolean);
  const direct = sentences.filter(line => !(
    /^(?:bu\s+(?:bir\s+)?(?:araç|kodlama|dosya).*?(?:soru|görev)|elimdeki araçlar|kullanılabilir araçlar|ajanlarım|benim araçlarım)/iu.test(line)
    || /^(?:kod,?\s+dosya|sana\s+kod).*?(?:araç|yardımcı)/iu.test(line)
    || /^(?:şu anki model|ben bir yapay zeka modeliyim).*\b(?:nemotron|gpt|claude|nvidia)\b/iu.test(line)
  )).join(" ").replace(/^(?:h+m+|m+h+m+)[\s,.…!?-]+/iu, "").trim();
  if (!/[\p{L}\p{N}]/u.test(direct)) return NO_SPOKEN_ANSWER;
  if (direct.length <= 480) return direct;
  const cut = direct.lastIndexOf(" ", 450);
  return `${direct.slice(0, cut > 0 ? cut : 450)}…${inChat ? " Ayrıntılar sohbette." : ""}`;
}
