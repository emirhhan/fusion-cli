import { pronounceEnglishInTurkish } from "./englishPronunciation";

// Keep the same pronunciation rules in the standalone Kits client.
const terms: Record<string, string> = {
  "chatgpt": "Çet Ci Pi Ti", "gpt": "Ci Pi Ti", "openai": "Opın Ey Ay",
  "fusion": "Füzyon", "motogate": "Moto Geyt", "motogeyt": "Moto Geyt",
  "python": "Paytın", "github": "Git Hab", "gitlab": "Git Leb", "vscode": "Vi Es Kod",
  "javascript": "Cava Skript", "typescript": "Tayp Skript", "docker": "Dokır",
  "c++": "Si Plus Plus", "c#": "Si Şarp", "html": "Eyç Ti Em El", "css": "Si Es Es",
  "api": "Ey Pi Ay", "ai": "Ey Ay", "http": "Eyç Ti Ti Pi", "https": "Eyç Ti Ti Pi Es",
  "json": "Ceyson", "sql": "Es Kyu El", "yaml": "Yemıl", "xml": "Eks Em El",
  "rest": "Rest", "graphql": "Graf Kyu El", "sdk": "Es Di Key", "cli": "Si El Ay",
  "ui": "Yu Ay", "ux": "Yu Eks", "cpu": "Si Pi Yu", "gpu": "Ci Pi Yu",
  "ram": "Rem", "ssd": "Es Es Di", "usb": "Yu Es Bi", "wifi": "Vay Fay",
  "pdf": "Pe De Fe", "csv": "Si Es Vi", "kvkk": "Ke Ve Ke Ke", "sgk": "Se Ge Ke",
  "tc": "Te Ce", "kobi": "Kobi", "llm": "El El Em", "tts": "Ti Ti Es",
  "stt": "Es Ti Ti", "url": "Yu Ar El", "dns": "Di En Es", "vpn": "Vi Pi En",
  "ip": "Ay Pi", "kpi": "Key Pi Ay", "roas": "Roas", "roi": "Ar Ou Ay",
  "macos": "Mek Ou Es", "ios": "Ay Ou Es", "windows": "Vindovs",
  "aws": "Ey Dabılyu Es", "oauth": "Ou Ot", "jwt": "Cey Dabılyu Ti",
  "web": "Veb", "llama": "Lama", "chatbot": "Çet Bot", "e2e": "uçtan uca",
  "pr": "Pi Ar", "seo": "Es İ Ou", "sms": "Es Em Es", "qr": "Kyu Ar",
  "tcp": "Ti Si Pi", "ssh": "Es Es Eyç", "ssl": "Es Es El", "tls": "Ti El Es",
};
const flexibleTerms = /(^|[^\p{L}\p{N}])((?:moto[ -]?(?:gate|geyt)|vs\s+code|wi[ -]?fi|c[+][+]|c#|openai|chatgpt|fusion|python|github|gitlab|javascript|typescript|docker|macos|windows|ios|oauth|web|llama|chatbot|e2e))(?:['’‘ʼ]([\p{L}]+))?(?=$|[^\p{L}\p{N}])/giu;
const acronym = /(^|[^\p{L}\p{N}])([A-Z]{2,8}|[Aa][Pp][Iiİi])(?:['’‘ʼ]([\p{L}]+))?(?=$|[^\p{L}\p{N}])/gu;

const suffixAfterAy: Record<string, string> = {
  ya: "a", ye: "a", yı: "ı", yi: "ı", yu: "ı", yü: "ı",
  sı: "ı", si: "ı", su: "ı", sü: "ı", nın: "ın", nin: "ın", nun: "ın", nün: "ın",
  de: "da", te: "da", ta: "da", den: "dan", ten: "dan", tan: "dan", deki: "daki", teki: "daki",
};

function attachSpokenSuffix(spoken: string, suffix?: string): string {
  if (!suffix) return spoken;
  const lower = suffix.toLocaleLowerCase("tr");
  if (/ay$/iu.test(spoken)) return spoken + (suffixAfterAy[lower] ?? lower);
  if (spoken === "Füzyon") {
    const endings: Record<string, string> = { ı: "u", i: "u", ın: "un", in: "un", e: "a", de: "da", den: "dan" };
    return spoken + (endings[lower] ?? lower);
  }
  return spoken + lower;
}

const abbreviations: Record<string, string> = {
  "a.ş.": "Anonim Şirketi", "t.c.": "Türkiye Cumhuriyeti",
  "dr.": "Doktor", "prof.": "Profesör", "doç.": "Doçent", "av.": "Avukat",
  "sn.": "Sayın", "örn.": "örneğin", "vb.": "ve benzeri", "vs.": "vesaire",
  "mah.": "Mahallesi", "cad.": "Caddesi", "sok.": "Sokağı", "no.": "numara",
};
const abbreviation = /(^|[^\p{L}\p{N}])(a\.ş\.|t\.c\.|dr\.|prof\.|doç\.|av\.|sn\.|örn\.|vb\.|vs\.|mah\.|cad\.|sok\.|no\.)(?!\p{L})/giu;

const units: Record<string, string> = {
  "km/s": "kilometre bölü saniye", "km/sa": "saatte kilometre",
  km: "kilometre", m: "metre", cm: "santimetre", mm: "milimetre",
  kg: "kilogram", g: "gram", mg: "miligram", l: "litre", ml: "mililitre",
  mb: "megabayt", gb: "gigabayt", tb: "terabayt", hz: "hertz",
  mhz: "megahertz", ghz: "gigahertz", ms: "milisaniye", tl: "lira",
};
const currencyNames: Record<string, string> = { "₺": "lira", "$": "dolar", "€": "avro", "£": "sterlin" };
const operators: Record<string, string> = {
  "+": "artı", "×": "çarpı", "÷": "bölü", "/": "bölü", "=": "eşittir",
  "<": "küçüktür", ">": "büyüktür", "≤": "küçük veya eşittir",
  "≥": "büyük veya eşittir", "≠": "eşit değildir", "−": "eksi",
};
const months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
  "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];

export function prepareTurkishSpeech(text: string): string {
  const knownPronunciations: string[] = [];
  const protect = (pronunciation: string) => `\uE000${knownPronunciations.push(pronunciation) - 1}\uE001`;
  const textWithKnownTerms = text.normalize("NFC")
    .replace(/[\uE000\uE001]/gu, " ")
    .replace(/!?\[([^\]]*)\]\([^)]+\)/gu, "$1")
    .replace(/https?:\/\/[^\s<>()]+(?<![.,!?;:])/giu, "bağlantı")
    .replace(/&(?:nbsp|#160);/giu, " ")
    .replace(/&(?:quot|apos|#39|#34);/giu, (value) => /apos|39/iu.test(value) ? "'" : '"')
    .replace(/&amp;/giu, "&")
    .replace(/<(?:\/?[a-z][a-z0-9-]*(?:\s+[^<>]*?)?\s*\/?)>/giu, " ")
    .replace(/^[ \t]*(?:[-*•▪◦]|\d+[.)])\s+/gmu, "")
    .replace(/^[ \t]*[|:\t -]+$/gmu, "")
    .replace(flexibleTerms, (_, prefix: string, term: string, suffix?: string) =>
      prefix + protect(attachSpokenSuffix(terms[term.toLowerCase().replace(/[\s-]+/gu, "")], suffix)))
    .replace(acronym, (original, prefix: string, token: string, suffix?: string) => {
      const spoken = terms[token.toLowerCase().replace(/\u0307/gu, "")];
      return spoken ? prefix + protect(attachSpokenSuffix(spoken, suffix)) : original;
    });
  return pronounceEnglishInTurkish(textWithKnownTerms)
    .replace(/\uE000(\d+)\uE001/gu, (_, index: string) => knownPronunciations[Number(index)])
    .replace(/(\d)\s*sn\.(?=\s|$)/giu, "$1 saniye")
    .replace(abbreviation, (_, prefix: string, word: string) => prefix + abbreviations[word.toLowerCase()])
    .replace(/\b(0?[1-9]|[12]\d|3[01])[./](0?[1-9]|1[0-2])[./]((?:19|20)\d{2})\b/gu,
      (_, day: string, month: string, year: string) => `${Number(day)} ${months[Number(month) - 1]} ${year}`)
    .replace(/\b(?:saat\s+)?([01]?\d|2[0-3]):([0-5]\d)\b/giu,
      (_, hour: string, minute: string) => `saat ${Number(hour)} ${Number(minute)}`)
    .replace(/^saat\b/u, "Saat")
    .replace(/\b\d{1,3}(?:[.\u202f\u00a0]\d{3})+(?=,\d|[^\d.]|$)/gu, (number) => number.replace(/\D/gu, ""))
    .replace(/\bv?\d+(?:\.\d+){2,}\b/giu, version =>
      version.replace(/^v/iu, "sürüm ").replace(/\./gu, ", "))
    .replace(/\b(\d+)\.(\d{1,2})(?!\d|\.\d)/gu, "$1,$2")
    .replace(/(\d)\s*-\s*(?=-?\d[^.!?\n]*=)/gu, "$1 eksi ")
    .replace(/(\d)\s+-(?=\s+\d)/gu, "$1 eksi")
    .replace(/(\d)\s*[–—-]\s*(?=\d)/gu, "$1 ila ")
    .replace(/(\d)\s*([+×÷=<>≤≥≠/−])\s*(?=[(−-]?\d)/gu,
      (_, number: string, operator: string) => number + " " + operators[operator] + " ")
    .replace(/(^|[\s([])[−-](?=\d)/gu, "$1eksi ")
    .replace(/(\d+(?:,\d+)?)\s*%(?!\s*\d)/gu, "yüzde $1")
    .replace(/%\s*(?=\d)/gu, "yüzde ")
    .replace(/(\d)\s*([₺$€£])/gu, (_, number: string, mark: string) => number + " " + currencyNames[mark])
    .replace(/([₺$€£])\s*(\d+(?:,\d+)?)/gu, (_, mark: string, number: string) => number + " " + currencyNames[mark])
    .replace(/(\d)\s*°\s*([CF])\b/giu,
      (_, number: string, scale: string) => number + (scale.toUpperCase() === "C" ? " santigrat derece" : " Fahrenhayt derece"))
    .replace(/(\d)\s*°/gu, "$1 derece")
    .replace(/(\d)\s*(km\/sa|km\/s|km|cm|mm|m|kg|mg|g|ml|l|mb|gb|tb|mhz|ghz|hz|ms|tl)\b/giu,
      (_, number: string, unit: string) => number + " " + units[unit.toLowerCase()])
    .replace(/(\d)['’‘ʼ](?=\p{L})/gu, "$1 ")
    .replace(/(\p{L})['’‘ʼ](?=\p{L})/gu, "$1")
    .replace(/[“”"'’‘ʼ«»„]/gu, "")
    .replace(/\s+[([{]\s*/gu, ", ")
    .replace(/[\])}]/gu, "")
    .replace(/\s*[–—]\s*|\s*[;:]\s*/gu, ", ")
    .replace(/[0-9#*]\uFE0F?\u20E3/gu, " ")
    .replace(/[\u{1F1E6}-\u{1F1FF}\uFE0F\u200D\u20E3]|\p{Extended_Pictographic}/gu, " ")
    .replace(/&(?!\w+;)/gu, " ve ")
    .replace(/[^\p{L}\p{N}\s.!?,…]/gu, " ")
    .replace(/\s+([.!?,…])/gu, "$1")
    .replace(/([.!?])(?:[.!?…]+)(?=\s|$)/gu, "$1")
    .replace(/(^|\s)[.!?,…]+(?=\s|$)/gu, "$1")
    .replace(/^\s*[.!?,…]+/u, "")
    .replace(/\s+/gu, " ").trim();
}
