let token = sessionStorage.getItem('fusion-kits-token') ?? '';
export function setToken(value: string) {
  token = value;
  if (value) sessionStorage.setItem('fusion-kits-token', value);
  else sessionStorage.removeItem('fusion-kits-token');
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
/** Sunucuya hiç ulaşılamadığında (yeniden başlarken, kapalıyken) gösterilen metin. */
export const UNREACHABLE_MESSAGE =
  'Kits sunucusuna ulaşılamadı; birkaç saniye sonra yeniden dene.';
/** Ağ katmanı hatası: Chromium "Failed to fetch", WebKit "Load failed",
 * Firefox "NetworkError…". Tarayıcının İngilizce metni kullanıcıya gösterilmez. */
export function isNetworkError(error: unknown) {
  return (
    error instanceof TypeError &&
    /failed to fetch|load failed|networkerror|network request failed/i.test(
      error.message,
    )
  );
}
/** Arayüzde gösterilecek hata metni; ağ hatası Türkçeleştirilir. */
export function errorText(error: unknown, fallback: string) {
  if (isNetworkError(error)) return UNREACHABLE_MESSAGE;
  if (error instanceof Error && /^failed to fetch$/i.test(error.message))
    return UNREACHABLE_MESSAGE;
  return error instanceof Error && error.message ? error.message : fallback;
}
/** Geliştirme vekili sunucu kapalıyken 502/504 döndürür. 503'ü Kits'in kendisi
 * (kurulum eksik vb.) kendi mesajıyla verir; o ulaşılamama sayılmaz. */
const GATEWAY_STATUSES = [502, 504];
const RETRY_DELAYS_MS = [400, 1200];
const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
async function send(
  path: string,
  method: string,
  body: unknown,
  signal?: AbortSignal,
) {
  // Yalnız okuma istekleri yeniden denenir; yazma isteği sunucuya ulaşmış
  // olabilir ve ikinci kez göndermek işi çoğaltır.
  const delays = ['GET', 'HEAD'].includes(method) ? RETRY_DELAYS_MS : [];
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(`/api${path}`, {
        method,
        signal,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(['GET', 'HEAD'].includes(method)
            ? {}
            : { 'Content-Type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      if (!GATEWAY_STATUSES.includes(response.status)) return response;
      if (attempt >= delays.length)
        throw new ApiError(UNREACHABLE_MESSAGE, response.status);
    } catch (error) {
      if (signal?.aborted || error instanceof ApiError) throw error;
      if (!isNetworkError(error)) throw error;
      if (attempt >= delays.length) throw new ApiError(UNREACHABLE_MESSAGE, 0);
    }
    await wait(delays[attempt], signal);
  }
}
export async function api<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await send(path, method, body, signal);
  const data = (await response
    .json()
    .catch(() => ({ error: 'Sunucu okunamayan bir yanıt döndürdü.' }))) as {
    error?: string;
  };
  if (!response.ok)
    throw new ApiError(
      data.error ?? `İstek başarısız oldu (${response.status}).`,
      response.status,
    );
  return data as T;
}
export function authHeaders(): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}
