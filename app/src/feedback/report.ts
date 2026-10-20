/**
 * Hata raporu ve geri bildirim — sunucusuz.
 *
 * Fusion'ın rapor toplayacağı bir sunucusu yok. Bunun yerine rapor, deponun
 * herkese açık GitHub Issues sayfasına ÖNCEDEN DOLDURULMUŞ bir adres olarak
 * açılır; kullanıcı gönderilecek metni tarayıcıda görür ve kendisi gönderir.
 * Hiçbir şey kullanıcı bilmeden dışarı çıkmaz.
 *
 * Gönderilen her metin önce `redact`'ten geçer: kullanıcı klasörü, API
 * anahtarları, Bearer token'ları ve e-posta adresleri rapora girmez.
 */

export const ISSUE_NEW_URL = "https://github.com/emirhhan/fusion-cli/issues/new";

/**
 * Tarayıcıların ve GitHub'ın güvenle kabul ettiği adres uzunluğu. GitHub
 * ~8 KB'nin üstündeki adresleri reddediyor; 7.000 karakter pay bırakır.
 */
export const ISSUE_URL_LIMIT = 7000;

/** Başlığın önekten sonraki en fazla uzunluğu; GitHub listesinde tek satır kalır. */
const TITLE_MAX = 80;

export type ReportKind = "hata" | "geri-bildirim";

export interface ReportInput {
  tur: ReportKind;
  /** Kullanıcının ya da hatanın kısa açıklaması. */
  mesaj: string;
  /** Yığın izi, çekirdek hata metni gibi teknik ayrıntı. */
  ayrinti?: string;
}

export interface ReportEnvironment {
  surum: string;
  platform: string;
}

/** Offline export contains only the visible user report; no diagnostic source is read. */
export function supportBundle(input: ReportInput, env: ReportEnvironment): string {
  return JSON.stringify({
    schemaVersion: 1,
    manifest: {
      collected: ["user_report", "app_version", "platform"],
      notCollected: ["credentials", "conversation_history", "tool_arguments", "raw_logs", "environment_variables", "browser_profiles"],
      networkRequests: 0,
    },
    report: reportBody(input, env),
  }, null, 2);
}

const GIZLENDI = "[gizlendi]";

const GIZLI_KALIPLAR: ReadonlyArray<readonly [RegExp, string]> = [
  [/-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----[\s\S]*?(?:-----END \1-----|$)/gi, GIZLENDI],
  // macOS/Linux kullanıcı klasörü: kullanıcı adı rapora girmez.
  [/\/(?:Users|home)\/[^/\s"'`]+/g, "~"],
  [/C:\\Users\\[^\\\s"'`]+/gi, "~"],
  [/Bearer\s+[A-Za-z0-9._~+/=-]+/g, `Bearer ${GIZLENDI}`],
  [/(?:["']?)[A-Za-z0-9_.-]*(?:api[_-]?key|access[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|auth[_-]?token|client[_-]?secret|credential|token|secret|password|passwd|authorization|private[_-]?key)[A-Za-z0-9_.-]*(?:["']?)\s*[:=]\s*(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|[^\s,}]+)/gi, GIZLENDI],
  // Sağlayıcı anahtarları: OpenAI/Anthropic (sk-…), NVIDIA (nvapi-…), Google (AIza…), GitHub (gh*_…).
  [/\b(?:sk|nvapi|gsk|xai)-[A-Za-z0-9_-]{12,}/g, GIZLENDI],
  [/\bAIza[0-9A-Za-z_-]{20,}/g, GIZLENDI],
  [/\bgh[pousr]_[A-Za-z0-9]{20,}/g, GIZLENDI],
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[e-posta]"],
];

/** Rapora girecek metinden kişisel ve gizli bilgiyi ayıkla. */
export function redact(text: string): string {
  let decoded = text;
  for (let pass = 0; pass < 2 && /%[0-9a-f]{2}/i.test(decoded); pass++) {
    decoded = decoded.replace(/(?:%[0-9a-f]{2})+/gi, (part) => {
      try { return decodeURIComponent(part); } catch { return GIZLENDI; }
    });
  }
  const urls = decoded.replace(/https?:\/\/[^\s"'<>`]+/gi, (raw) => {
    try {
      const url = new URL(raw);
      url.username = "";
      url.password = "";
      url.search = "";
      url.hash = "";
      return url.toString();
    } catch { return GIZLENDI; }
  });
  return GIZLI_KALIPLAR.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), urls);
}

function titleFor({ tur, mesaj }: ReportInput): string {
  const onek = tur === "hata" ? "[Hata]" : "[Geri bildirim]";
  const ilkSatir = redact(mesaj).trim().split("\n")[0]?.trim() || (tur === "hata" ? "Fusion hatası" : "Fusion geri bildirimi");
  const kisa = ilkSatir.length > TITLE_MAX ? `${ilkSatir.slice(0, TITLE_MAX - 1)}…` : ilkSatir;
  return `${onek} ${kisa}`;
}

/** Issue gövdesi: açıklama, isteğe bağlı teknik ayrıntı ve ortam. */
export function reportBody(input: ReportInput, env: ReportEnvironment, ayrintiOverride?: string): string {
  const ayrinti = ayrintiOverride ?? (input.ayrinti ? redact(input.ayrinti).trim() : "");
  const parcalar = [
    input.tur === "hata" ? "### Ne oldu?" : "### Geri bildirim",
    redact(input.mesaj).trim() || "_(açıklama yazılmadı)_",
  ];
  if (ayrinti) parcalar.push("### Teknik ayrıntı", "```text", ayrinti, "```");
  parcalar.push("### Ortam", `- Fusion: ${env.surum}`, `- Sistem: ${env.platform}`, "", "_Fusion içinden gönderildi._");
  return redact(parcalar.join("\n"));
}

function issueUrl(title: string, body: string): string {
  const params = new URLSearchParams({ title, body });
  return `${ISSUE_NEW_URL}?${params.toString()}`;
}

/**
 * Önceden doldurulmuş GitHub issue adresi. Adres sınırı aşılırsa teknik
 * ayrıntı sondan kısaltılır; açıklama ve ortam bilgisi her zaman korunur.
 */
export function buildIssueUrl(input: ReportInput, env: ReportEnvironment): string {
  const title = titleFor(input);
  const tamUrl = issueUrl(title, reportBody(input, env));
  if (tamUrl.length <= ISSUE_URL_LIMIT || !input.ayrinti) return tamUrl;

  const ayrinti = redact(input.ayrinti).trim();
  const not = "\n… (uzun olduğu için kısaltıldı)";
  let alt = 0;
  let ust = ayrinti.length;
  // Kodlanmış uzunluk karaktere göre doğrusal değil; sığan en uzun öneki ikili arama bulur.
  while (alt < ust) {
    const orta = Math.ceil((alt + ust) / 2);
    const aday = issueUrl(title, reportBody(input, env, ayrinti.slice(0, orta) + not));
    if (aday.length <= ISSUE_URL_LIMIT) alt = orta;
    else ust = orta - 1;
  }
  return issueUrl(title, reportBody(input, env, ayrinti.slice(0, alt) + not));
}
