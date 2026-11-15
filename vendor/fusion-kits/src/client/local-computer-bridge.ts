import { parentOrigins } from './scheduled-delivery-bridge';

type Api = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
interface View {
  parent: Window;
  self: Window;
  addEventListener(
    type: 'message',
    listener: (event: MessageEvent) => void,
  ): void;
  removeEventListener(
    type: 'message',
    listener: (event: MessageEvent) => void,
  ): void;
}
export interface LocalComputerResult {
  status: string;
  snapshotId?: string | null;
  text?: string;
}
/** Kullanıcı Fusion'ın izin penceresini yanıtlayana dek beklenir. */
const DEFAULT_TIMEOUT_MS = 120_000;

/** Fusion uygulamasından (host) salt okunur bilgisayar gözlemi iste.
 * Yanıt yalnız izinli host kökeninden, aynı pencereden ve aynı nonce ile kabul edilir. */
export async function requestLocalComputer(
  view: View,
  api: Api,
  reason: string,
  options: { nonce?: () => string; timeoutMs?: number } = {},
): Promise<LocalComputerResult> {
  if (view.parent === view.self)
    return {
      status: 'unavailable',
      text: 'Kits Fusion uygulamasının içinde açık değil; bilgisayara bakılamaz.',
    };
  let origins: string[];
  try {
    origins = await parentOrigins(api);
  } catch {
    return { status: 'unavailable', text: 'Host politikası alınamadı.' };
  }
  const nonce = (options.nonce ?? (() => crypto.randomUUID()))();
  return new Promise((resolve) => {
    const done = (result: LocalComputerResult) => {
      clearTimeout(timer);
      view.removeEventListener('message', onMessage);
      resolve(result);
    };
    const onMessage = (event: MessageEvent) => {
      if (event.source !== view.parent || !origins.includes(event.origin))
        return;
      const data = event.data as Record<string, unknown> | null;
      if (
        !data ||
        data.type !== 'fusion-computer-result' ||
        data.nonce !== nonce ||
        typeof data.status !== 'string'
      )
        return;
      done({
        status: data.status,
        snapshotId:
          typeof data.snapshotId === 'string' ? data.snapshotId : null,
        text: typeof data.text === 'string' ? data.text : '',
      });
    };
    const timer = setTimeout(
      () =>
        done({
          status: 'unavailable',
          text: 'Fusion uygulaması süre içinde yanıt vermedi.',
        }),
      options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    );
    view.addEventListener('message', onMessage);
    // Yalnız izinli kökenlere gönderilir; ebeveyn başka kökendeyse tarayıcı teslim etmez.
    for (const origin of origins)
      view.parent.postMessage(
        { type: 'fusion-computer-request', nonce, reason },
        origin,
      );
  });
}
