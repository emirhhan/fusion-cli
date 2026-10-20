import type { IstekFn } from "./akisCalistir";

type Payload = Record<string, unknown>;
export interface ImageJobObservation {
  /** Yoksa yalnız var olan iş okunur; hiçbir üretim başlatılmaz. */
  start?: Payload;
  signal?: AbortSignal;
  onState?: (payload: Payload) => void;
  intervalMs?: number;
  requestTimeoutMs?: number;
  maxPolls?: number;
}

const STATES = new Set(["accepted", "running", "completed", "failed", "cancelled", "recoveryRequired"]);
const ACTIVE = new Set(["accepted", "running"]);

function uncertain(jobId: string, stopped = false): Payload {
  return {
    ok: false, jobId, state: "recoveryRequired",
    code: stopped ? "observation_stopped" : "observation_lost",
    metin: stopped
      ? "İş takibi durdu; üretim iptal edilmiş sayılmaz. Aynı iş kimliğiyle durumunu yeniden kontrol et."
      : "İşin sonucu doğrulanamadı. Yeniden üretmeden önce aynı iş kimliğiyle durumunu kontrol et.",
  };
}

function valid(payload: Payload, jobId: string): boolean {
  if (payload.jobId !== jobId || typeof payload.state !== "string" || !STATES.has(payload.state)) return false;
  if (ACTIVE.has(payload.state)) return payload.ok === true;
  if (payload.state !== "completed") return payload.ok === false;
  if (payload.ok !== true || !Array.isArray(payload.dosyalar) || !payload.dosyalar.length || payload.dosyalar.length > 16) return false;
  const paths = new Set<string>();
  return payload.dosyalar.every((item: unknown) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const file = item as Payload;
    if (typeof file.yol !== "string" || !/^(\/|[A-Za-z]:[\\/])/.test(file.yol) || paths.has(file.yol)) return false;
    if (!Number.isSafeInteger(file.genislik) || Number(file.genislik) <= 0
      || !Number.isSafeInteger(file.yukseklik) || Number(file.yukseklik) <= 0
      || typeof file.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(file.sha256)) return false;
    paths.add(file.yol);
    return true;
  });
}

/** Geç RPC yanıtı gözlemin sonucunu değiştiremez; bütün yerel zamanlayıcılar temizlenir. */
function bounded<T>(operation: () => Promise<T>, timeout: number, signal?: AbortSignal): Promise<T | undefined> {
  return new Promise((resolve) => {
    if (signal?.aborted) { resolve(undefined); return; }
    let settled = false;
    const finish = (value: T | undefined) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", aborted);
      resolve(value);
    };
    const aborted = () => finish(undefined);
    const timer = setTimeout(aborted, timeout);
    signal?.addEventListener("abort", aborted, { once: true });
    try { void operation().then(finish, () => finish(undefined)); }
    catch { finish(undefined); }
  });
}

function pause(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted || ms === 0) { resolve(); return; }
    const done = () => { clearTimeout(timer); signal?.removeEventListener("abort", done); resolve(); };
    const timer = setTimeout(done, ms);
    signal?.addEventListener("abort", done, { once: true });
  });
}

/** Tek başlatma, sınırlı durum gözlemi. ACK kaybı hiçbir zaman yeni sağlayıcı çağrısı değildir. */
export async function observeImageJob(request: IstekFn, jobId: string, options: ImageJobObservation = {}): Promise<Payload> {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(jobId)) return uncertain(jobId);
  const timeout = Math.min(30000, Math.max(1, options.requestTimeoutMs ?? 10000));
  const polls = Math.min(2400, Math.max(1, Math.floor(options.maxPolls ?? 1200)));
  const interval = Math.min(10000, Math.max(0, options.intervalMs ?? 1000));
  if (options.signal?.aborted) return uncertain(jobId, true);
  let response = options.start === undefined ? undefined
    : await bounded(() => request("gorsel.is.baslat", { ...options.start, requestId: jobId }), timeout, options.signal);
  for (let index = 0; index < polls; index++) {
    if (options.signal?.aborted) return uncertain(jobId, true);
    if (response !== undefined) {
      if (!valid(response, jobId)) return uncertain(jobId);
      options.onState?.(response);
      if (!ACTIVE.has(String(response.state))) return response;
    }
    response = await bounded(() => request("gorsel.is.durum", { jobId }), timeout, options.signal);
    // Son sorgunun terminal cevabı da bütçe dolmadan işlenir.
    if (response !== undefined && valid(response, jobId) && !ACTIVE.has(String(response.state))) {
      options.onState?.(response);
      return response;
    }
    if (index + 1 < polls) await pause(interval, options.signal);
  }
  return uncertain(jobId, options.signal?.aborted);
}

export async function cancelImageJob(request: IstekFn, jobId: string, options: ImageJobObservation = {}): Promise<Payload> {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(jobId)) return uncertain(jobId);
  const response = await bounded(() => request("gorsel.is.iptal", { jobId }), options.requestTimeoutMs ?? 10000, options.signal);
  return response !== undefined && valid(response, jobId) && !ACTIVE.has(String(response.state))
    ? response : uncertain(jobId, options.signal?.aborted);
}

export interface ImageJobSummary { jobId: string; state: string }
export async function readImageJobPage(request: IstekFn, cursor: string, signal?: AbortSignal): Promise<{ jobs: ImageJobSummary[]; next: string | null }> {
  const response = await bounded(() => request("gorsel.is.liste", { limit: 50, ...(cursor ? { sonraki: cursor } : {}) }), 10000, signal);
  if (!response || response.ok !== true || !Array.isArray(response.isler) || response.isler.length > 50
    || (response.sonraki !== null && (typeof response.sonraki !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(response.sonraki)))) {
    throw new Error("Görsel işlerinin durumu okunamadı; yeni üretim başlatılmadı.");
  }
  const jobs = response.isler.map((item: unknown) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error("Görsel iş kaydı geçersiz.");
    const summary = item as Payload;
    if (typeof summary.jobId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(summary.jobId)
      || typeof summary.state !== "string" || !STATES.has(summary.state) || summary.outputsVerified !== false) {
      throw new Error("Görsel iş kaydı geçersiz.");
    }
    return { jobId: summary.jobId, state: summary.state };
  });
  return { jobs, next: response.sonraki as string | null };
}
