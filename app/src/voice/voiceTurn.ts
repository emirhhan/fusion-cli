import type { VoiceTurnMetadata } from "../sessions/types";
import type { Mesaj } from "../screens/Conversation";
import type { VoiceRuntimeState } from "./bridge";
import type { ProtocolClient } from "../protocol/client";
import type { SideTurn } from "../sidechat/SideChat";
import { formatVoiceDate, isSpokenWorkRequest, normalizeSpokenNames, normalizeVoiceWords, NO_SPOKEN_ANSWER, spokenTeacherAnswer, stripVoiceToolMarkup } from "./localVoice";
import { splitIntoSentences } from "./sentenceStream";

interface VoiceClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

export interface VoiceTurnHandle {
  id: string;
  cancel(): Promise<void>;
  finished: Promise<void>;
}

export function findVoiceAnswer(messages: Mesaj[], afterIndex: number): string | null {
  for (let index = messages.length - 1; index >= afterIndex; index -= 1) {
    const message = messages[index];
    if (message.rol === "asistan" && message.metin.trim()) return message.metin.trim();
  }
  return null;
}

/** Sesli söz de aynı model turuna gider; kesilen yanıtın bağlamı korunur. */
export function buildVoiceRequest(text: string, interrupted?: string): {
  text: string; voice: VoiceTurnMetadata;
} {
  return { text, voice: interrupted ? { kesilen: interrupted } : {} };
}

const voiceDomain = /\b[\p{L}\p{N}][\p{L}\p{N}-]*(?:\.[\p{L}\p{N}-]+)*\.(?:com|net|org|tr|io|co|ai|gov|edu)(?:\.[a-z]{2})?\b/iu;

export function followupVoiceResearch(text: string, previous?: string): string | null {
  if (!previous) return null;
  const words = normalizeVoiceWords(text);
  const followup = /^(?:(?:peki|hayir|lutfen|bu bilgiyi|bunu|buna|bir de|bu konuyu|bir daha|tekrar|yeniden|tam|detayli|ayrintili|iyice) )*(?:kontrol et|arastir|dogrula|kaynak bul|bak)(?:(?:ebilir|abilir|ar|er|ur|ir) misin)?(?: lutfen)?$/u;
  if (followup.test(words)) return normalizeSpokenNames(previous);
  const location = text.trim().match(/^(?:peki\s+)?(?:((?:[\p{L}]+[ -]){0,2}[\p{L}]+['’](?:daki|deki|taki|teki|da|de|ta|te))\s+)?(?:mağazası|şubesi|adresi)[\p{L}]*(?![\p{L}\p{N}])/iu);
  if (!location) return null;
  const locationTail = normalizeVoiceWords(text.trim().slice(location[0].length));
  if (!/^(?:(?:adres|adresi) )?(?:n|ne|nedir|nerede|nerededir|var mi)?$/u.test(locationTail)) return null;
  const known = normalizeSpokenNames(previous.trim());
  const entity = known.match(voiceDomain)?.[0] ??
    known.match(/^([\p{L}\p{N}][\p{L}\p{N} .&-]{0,70}?)\s+(?:güvenilir|güvenli|dolandırıcı)\s+m[ıi]\b/iu)?.[1];
  if (!entity) return null;
  return `${entity}${location[1] ? " " + location[1] : ""} ${locationTail === "var mi" ? "mağazası var mı?" : "mağazasının adresi nedir?"}`;
}

export function incompleteVoiceRequest(text: string): boolean {
  // ASR sometimes finalizes directly after the article (“... bir”).
  return /\S+\s+(?:bir|bi)\s*$/iu.test(text.trim().replace(/[.!?…]+$/u, ""));
}

export function needsVoiceResearch(text: string, now = new Date()): boolean {
  const words = normalizeVoiceWords(text);
  if (isSpokenWorkRequest(text) && /\b(?:proje\w*|dosya\w*|klasor\w*|dizin\w*|repo\w*|terminal\w*|bilgisayar\w*)\b/u.test(words)) return false;
  if (voiceDomain.test(text) || /\bnokta (?:com|kom|net|org|tr)\b/u.test(words)) return true;
  if (/\b(?:ticari unvan\w*|sirket\w* unvan\w*|kime ait|kim isletiyor|sahibi kim)\b/u.test(words)) return true;
  if (/\b(?:guvenilir mi|guvenli mi|dolandirici mi|sikayet\w* var mi)\b/u.test(words)
    && !/\b(?:surumum|dosyam|klasorum|kodum|bilgisayarim|projem)\b/u.test(words)) return true;
  if (/\b(?:internette|webde|resmi kaynaklardan|guncel kaynaklardan)\b.*\b(?:ara|arastir|bak|dogrula|kontrol et|bul)\b/u.test(words)) return true;
  const recent = new RegExp(`\\b(?:${now.getFullYear()}|${now.getFullYear() - 1}|bu yil|son bir yil|son aylarda|son haftalarda|en son|guncel|bugun|su an)\\b`, "u");
  return recent.test(words) &&
    /\b(?:degis\w*|guncelle\w*|yenilik\w*|duyur\w*|lansman\w*|haber\w*|durum\w*|gelism\w*|performans\w*|fiyat\w*|neler oldu)\b/u.test(words);
}

const RESEARCH_NEEDED = "GUNCEL_KAYNAK_GEREKIYOR";

export function voiceAnswerNeedsResearch(answer: string): boolean {
  if (answer.trim() === RESEARCH_NEEDED) return true;
  const words = normalizeVoiceWords(answer);
  return /\b(?:20\d{2}|guncel(?: bilgilere| veriye)?|son gelismelere)\b.{0,95}\b(?:bilgim yok|bilgiye sahip degilim|erisimim yok|dogrulayamiyorum)\b/u.test(words);
}

export async function askVoiceResearch(
  client: Pick<ProtocolClient, "request">,
  text: string,
  signal: AbortSignal,
  detailed = false,
): Promise<string> {
  const result = await client.request("ses.arastir", { soru: text, ...(detailed ? { ayrintili: true } : {}) }, { signal, timeoutMs: 24_000 });
  return typeof result.metin === "string" && result.metin.trim()
    ? result.metin.trim() : "Arka plan aramasından yanıt alamadım.";
}

export async function askVoiceQuestion(
  client: Pick<ProtocolClient, "request">,
  text: string,
  history: SideTurn[],
  signal: AbortSignal,
): Promise<string> {
  const prompt = `Kullanıcının cihazındaki bugünün tarihi ${formatVoiceDate(new Date())}. Türkçe ve konuşma dilinde yanıtla. Ayrıntı istenmedikçe bir veya iki kısa cümle kullan. Araç çağrısı, kod bloğu ve iç protokol yazma. Güncel, kurumsal ya da kamusal bir iddiayı doğrulayamıyorsan yalnızca ${RESEARCH_NEEDED} yaz.`;
  const normalized = normalizeSpokenNames(text);
  const start = performance.now();
  const ask = (instruction: string, previous: SideTurn[], timeoutMs = 15_000) => client.request("yan_sohbet.sor", {
    soru: `${instruction}\n\n${normalized}`,
    gecmis: previous,
    tarayicisiz: true,
  }, { signal, timeoutMs });
  const read = (result: Record<string, unknown>): string => (
    result.ok === true && typeof result.metin === "string" ? result.metin.trim() : ""
  );
  const first = read(await ask(prompt, history));
  if (!first) throw new Error("Kısa soruya yanıt alınamadı.");
  if (voiceAnswerNeedsResearch(first) || spokenTeacherAnswer(first, false) !== NO_SPOKEN_ANSWER) return first;
  if (signal.aborted || performance.now() - start >= 13_000) {
    return "Bu soruya yanıt veremedim. Biraz farklı şekilde sorabilir misin?";
  }
  // Only prior usable turns belong in the retry, never the generated tool output.
  const safeHistory = history.map(turn => ({ ...turn, metin: stripVoiceToolMarkup(turn.metin).trim() }))
    .filter(turn => turn.metin);
  const second = read(await ask(`${prompt} Kullanıcıya doğrudan düz yazıyla cevap ver; komut veya işaret üretme.`, safeHistory,
    Math.max(1, Math.ceil(15_000 - (performance.now() - start)))));
  if (voiceAnswerNeedsResearch(second) || spokenTeacherAnswer(second, false) !== NO_SPOKEN_ANSWER) return second;
  return "Bu soruya yanıt veremedim. Biraz farklı şekilde sorabilir misin?";
}

export async function speakVoiceAnswer(
  client: VoiceClient,
  text: string,
  publish: (state: VoiceRuntimeState) => Promise<void>,
): Promise<VoiceTurnHandle> {
  await publish({ durum: "talking", metin: text });
  try {
    const result = await client.request("ses.konus", { metin: text });
    const id = typeof result.tur_id === "string" ? result.tur_id : "";
    if (result.ok !== true || !id) {
      throw new Error(
        typeof result.metin === "string" ? result.metin : "Sesli yanıt başlatılamadı.",
      );
    }
    let cancelled = false;
    let settled = false;
    let cancellation: Promise<void> | null = null;
    const finished = client.request("ses.bekle", { tur_id: id }).then(async (completion) => {
      settled = true;
      if (cancelled) return;
      if (completion.ok !== true || completion.tamamlandi !== true) {
        throw new Error(
          typeof completion.metin === "string"
            ? completion.metin
            : "Sesli yanıt tamamlanamadı.",
        );
      }
      await publish({ durum: "listening" });
    }).catch(async (reason) => {
      settled = true;
      if (cancelled) return;
      await publish({ durum: "error", metin: errorText(reason) });
      throw reason;
    });

    return {
      id,
      finished,
      cancel: () => {
        if (cancellation) return cancellation;
        if (settled) return Promise.resolve();
        cancelled = true;
        const cancellationStartedAt = performance.now();
        cancellation = client.request("ses.durdur", { tur_id: id }).then(async (stopped) => {
          if (stopped.ok !== true) {
            throw new Error(
              typeof stopped.metin === "string" ? stopped.metin : "Sesli yanıt kesilemedi.",
            );
          }
          if (import.meta.env.DEV) {
            console.debug("[talk] TTS cancellation acknowledged", {
              elapsed_ms: performance.now() - cancellationStartedAt,
              tur_id: id,
            });
          }
          await publish({ durum: "interrupted" });
          await publish({ durum: "listening" });
        }).catch(async (reason) => {
          await publish({ durum: "error", metin: errorText(reason) });
          throw reason;
        });
        return cancellation;
      },
    };
  } catch (reason) {
    await publish({ durum: "error", metin: errorText(reason) });
    throw reason;
  }
}

/**
 * `speakVoiceAnswer` gibi ama TEK büyük TTS turu yerine cevabı cümlelere
 * bölüp AYRI turlar hâlinde art arda seslendirir.
 *
 * Neden: `ses.konus` tüm metni ses motoruna TEK seferde verir ve konuşma ancak
 * TÜM metin sentezlendikten sonra başlar (bkz. `appserver/voice.py::speak`).
 * Uzun bir cevapta bu, kullanıcının sesi duymadan önce sentezin TAMAMINI
 * beklemesi demektir. Cümle cümle göndermek ilk sesin, YALNIZ ilk cümle
 * sentezlenince başlamasını sağlar; geri kalan cümleler bir öncekinin
 * çalması sürerken zaten sıradadır.
 *
 * `VoiceTurnHandle` sözleşmesi DEĞİŞMEZ: `cancel()` o an çalan cümleyi durdurup
 * kalan kuyruğu iptal eder, `finished` yalnız SON cümle bitince (ya da iptalde
 * hemen) çözülür — çağıran taraf (`SessionApplication.tsx`) tek bir tur
 * yönetiyormuş gibi davranmaya devam edebilir.
 */
export async function speakVoiceAnswerStreamed(
  client: VoiceClient,
  text: string,
  publish: (state: VoiceRuntimeState) => Promise<void>,
): Promise<VoiceTurnHandle> {
  await publish({ durum: "talking", metin: text });
  try {
    const sentences = splitIntoSentences(text);
    const queue = sentences.length > 0 ? sentences : [text];

    let cancelled = false;
    let settled = false;
    let cancellation: Promise<void> | null = null;
    let currentTurnId = "";
    // Uçuştaki `ses.konus`: iptal bunu beklemeden `currentTurnId` ile durdurursa geç dönen tur
    // kimsenin sahipliğinde kalır ve çalmaya devam eder (ölçüldü, 29 Ekim).
    let starting: Promise<unknown> | null = null;

    const startSentence = async (sentence: string): Promise<string> => {
      const request = client.request("ses.konus", { metin: sentence });
      starting = request.catch(() => undefined);
      const result = await request;
      starting = null;
      const id = typeof result.tur_id === "string" ? result.tur_id : "";
      if (result.ok !== true || !id) {
        throw new Error(
          typeof result.metin === "string" ? result.metin : "Sesli yanıt başlatılamadı.",
        );
      }
      currentTurnId = id;
      return id;
    };

    const waitSentence = async (id: string): Promise<void> => {
      const completion = await client.request("ses.bekle", { tur_id: id });
      // Bu bekleme `cancel()` tarafından KASITLI olarak kesilmiş olabilir;
      // o durumda `tamamlandi: false` bir hata değil, iptalin kendisidir.
      if (cancelled) return;
      if (completion.ok !== true || completion.tamamlandi !== true) {
        throw new Error(
          typeof completion.metin === "string"
            ? completion.metin
            : "Sesli yanıt tamamlanamadı.",
        );
      }
    };

    currentTurnId = await startSentence(queue[0]);

    const finished = (async () => {
      await waitSentence(currentTurnId);
      for (let index = 1; index < queue.length && !cancelled; index += 1) {
        currentTurnId = await startSentence(queue[index]);
        if (cancelled) break;
        await waitSentence(currentTurnId);
      }
    })().then(async () => {
      settled = true;
      if (cancelled) return;
      await publish({ durum: "listening" });
    }).catch(async (reason) => {
      settled = true;
      if (cancelled) return;
      await publish({ durum: "error", metin: errorText(reason) });
      throw reason;
    });

    return {
      id: currentTurnId,
      finished,
      cancel: () => {
        if (cancellation) return cancellation;
        if (settled) return Promise.resolve();
        cancelled = true;
        cancellation = Promise.resolve(starting).then(
          () => client.request("ses.durdur", { tur_id: currentTurnId }),
        ).then(
          async (stopped) => {
            if (stopped.ok !== true) {
              throw new Error(
                typeof stopped.metin === "string" ? stopped.metin : "Sesli yanıt kesilemedi.",
              );
            }
            await publish({ durum: "interrupted" });
            await publish({ durum: "listening" });
          },
        ).catch(async (reason) => {
          await publish({ durum: "error", metin: errorText(reason) });
          throw reason;
        });
        return cancellation;
      },
    };
  } catch (reason) {
    await publish({ durum: "error", metin: errorText(reason) });
    throw reason;
  }
}
