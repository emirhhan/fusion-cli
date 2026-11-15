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
/** Kullanıcı yerel klasör penceresinde seçim yapana dek beklenir. */
const DEFAULT_TIMEOUT_MS = 300_000;

/** Fusion uygulamasından yerel klasör seçicisini aç; seçilen yolu döndür.
 * Kits Fusion içinde değilse ya da kullanıcı vazgeçerse `null`. Yanıt yalnız
 * izinli host kökeninden, aynı pencereden ve aynı nonce ile kabul edilir. */
export async function requestFolder(
  view: View,
  api: Api,
  options: { nonce?: () => string; timeoutMs?: number } = {},
): Promise<string | null> {
  if (view.parent === view.self) return null;
  let origins: string[];
  try {
    origins = await parentOrigins(api);
  } catch {
    return null;
  }
  const nonce = (options.nonce ?? (() => crypto.randomUUID()))();
  return new Promise((resolve) => {
    const done = (path: string | null) => {
      clearTimeout(timer);
      view.removeEventListener('message', onMessage);
      resolve(path);
    };
    const onMessage = (event: MessageEvent) => {
      if (event.source !== view.parent || !origins.includes(event.origin))
        return;
      const data = event.data as Record<string, unknown> | null;
      if (!data || data.type !== 'fusion-folder-result' || data.nonce !== nonce)
        return;
      done(typeof data.path === 'string' && data.path ? data.path : null);
    };
    const timer = setTimeout(
      () => done(null),
      options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    );
    view.addEventListener('message', onMessage);
    for (const origin of origins)
      view.parent.postMessage({ type: 'fusion-folder-request', nonce }, origin);
  });
}

/** Seçilen klasörün adından proje adı önerir (izinli karakterlere indirger). */
export function suggestProjectName(path: string): string {
  const base =
    path
      .replace(/[\\/]+$/, '')
      .split(/[\\/]/)
      .pop() ?? '';
  return base.replace(/[^\p{L}\p{N}_.-]+/gu, '-').slice(0, 64);
}
