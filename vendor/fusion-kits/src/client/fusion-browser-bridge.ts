import { parentOrigins } from './scheduled-delivery-bridge';
import type {
  FusionBrowserInput,
  FusionBrowserResult,
} from '../shared/fusion-browser';

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
/** Kullanıcının izin penceresi (en çok birkaç dakika) + eklenti komut zaman aşımı (30 sn). */
const DEFAULT_TIMEOUT_MS = 180_000;
const STATUSES: ReadonlySet<FusionBrowserResult['status']> = new Set([
  'ok',
  'denied',
  'busy',
  'failed',
  'unavailable',
]);

/** İsteği yapan Kit; Fusion onay penceresinde adını gösterir ve okuma iznini Kit başına tutar. */
export interface FusionBrowserKit {
  id: string;
  name: string;
}

/** Fusion hostundan (ebeveyn pencere) Chrome eklentisi komutu iste.
 * Yanıt yalnız izinli host kökeninden, aynı pencereden ve aynı nonce ile kabul edilir;
 * `local-computer-bridge.ts` ile aynı güven modeli. `kit` Kits uygulamasının bildirdiği
 * kimliktir (Kit'in modelinden gelmez); Fusion bunu pencerede "«Kod» Kit'i" diye gösterir. */
export async function requestFusionBrowser(
  view: View,
  api: Api,
  input: FusionBrowserInput,
  options: {
    nonce?: () => string;
    timeoutMs?: number;
    kit?: FusionBrowserKit;
  } = {},
): Promise<FusionBrowserResult> {
  if (view.parent === view.self)
    return {
      status: 'unavailable',
      text: 'Kits Fusion uygulamasının içinde açık değil; Chrome eklentisi kullanılamaz.',
    };
  let origins: string[];
  try {
    origins = await parentOrigins(api);
  } catch {
    return { status: 'unavailable', text: 'Host politikası alınamadı.' };
  }
  const nonce = (options.nonce ?? (() => crypto.randomUUID()))();
  return new Promise((resolve) => {
    const done = (result: FusionBrowserResult) => {
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
        data.type !== 'fusion-browser-result' ||
        data.nonce !== nonce ||
        typeof data.status !== 'string' ||
        !STATUSES.has(data.status as FusionBrowserResult['status'])
      )
        return;
      done({
        status: data.status as FusionBrowserResult['status'],
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
    for (const origin of origins)
      view.parent.postMessage(
        {
          type: 'fusion-browser-request',
          nonce,
          input,
          ...(options.kit
            ? { kit: { id: options.kit.id, name: options.kit.name } }
            : {}),
        },
        origin,
      );
  });
}
