import { parentOrigins } from './scheduled-delivery-bridge';
import type { FusionBrowserResult } from '../shared/fusion-browser';
import {
  sessionStateSchema,
  type FusionProfileInput,
} from '../shared/fusion-profile';

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
/** Kullanıcının onay penceresi birkaç dakika açık kalabilir. */
const DEFAULT_TIMEOUT_MS = 180_000;
const STATUSES: ReadonlySet<FusionBrowserResult['status']> = new Set([
  'ok',
  'denied',
  'busy',
  'failed',
  'unavailable',
]);

export interface FusionProfileKit {
  id: string;
  name: string;
}

interface HostReply {
  status: FusionBrowserResult['status'];
  text: string;
  state?: unknown;
}

/** Fusion hostundan profil oturumu iste; yanıt yalnız izinli kökenden, aynı nonce ile kabul edilir. */
function askHost(
  view: View,
  origins: string[],
  nonce: string,
  input: FusionProfileInput,
  kit: FusionProfileKit | undefined,
  timeoutMs: number,
): Promise<HostReply> {
  return new Promise((resolve) => {
    const done = (result: HostReply) => {
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
        data.type !== 'fusion-profile-result' ||
        data.nonce !== nonce ||
        typeof data.status !== 'string' ||
        !STATUSES.has(data.status as FusionBrowserResult['status'])
      )
        return;
      done({
        status: data.status as FusionBrowserResult['status'],
        text: typeof data.text === 'string' ? data.text : '',
        state: data.state,
      });
    };
    const timer = setTimeout(
      () =>
        done({
          status: 'unavailable',
          text: 'Fusion uygulaması süre içinde yanıt vermedi.',
        }),
      timeoutMs,
    );
    view.addEventListener('message', onMessage);
    for (const origin of origins)
      view.parent.postMessage(
        {
          type: 'fusion-profile-request',
          nonce,
          input,
          ...(kit ? { kit: { id: kit.id, name: kit.name } } : {}),
        },
        origin,
      );
  });
}

/**
 * Fusion profilini bu Kit'in tarayıcısına yükle (P-023). Oturum (`state`) yalnız bu
 * fonksiyonun yerel değişkeninde durur ve doğrudan Kit bilgisayarına gider; dönüş değeri
 * (Kit'in modeline giden araç sonucu) yalnız özet metindir. Hiçbir şey loglanmaz.
 */
export async function requestFusionProfile(
  view: View,
  api: Api,
  dotId: string,
  input: FusionProfileInput,
  options: {
    nonce?: () => string;
    timeoutMs?: number;
    kit?: FusionProfileKit;
  } = {},
): Promise<FusionBrowserResult> {
  if (view.parent === view.self)
    return {
      status: 'unavailable',
      text: 'Kits Fusion uygulamasının içinde açık değil; Fusion profilleri kullanılamaz.',
    };
  let origins: string[];
  try {
    origins = await parentOrigins(api);
  } catch {
    return { status: 'unavailable', text: 'Host politikası alınamadı.' };
  }
  const nonce = (options.nonce ?? (() => crypto.randomUUID()))();
  const reply = await askHost(
    view,
    origins,
    nonce,
    input,
    options.kit,
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );
  if (reply.status !== 'ok') return { status: reply.status, text: reply.text };
  const parsed = sessionStateSchema.safeParse(reply.state);
  if (!parsed.success)
    return { status: 'failed', text: 'Fusion geçersiz bir oturum döndürdü.' };
  try {
    const loaded = await api<{ cookies?: number; error?: unknown }>(
      `/dots/${encodeURIComponent(dotId)}/computer/actions`,
      'POST',
      {
        action: 'session_load',
        input: {
          profile: input.profile,
          domains: input.domains,
          state: parsed.data,
        },
      },
    );
    // Yerel bilgisayar işlem hatasını 200 + `{error}` ile döndürür.
    if (typeof loaded.error === 'string') throw new Error(loaded.error);
    const count =
      typeof loaded.cookies === 'number'
        ? loaded.cookies
        : parsed.data.cookies.length;
    return {
      status: 'ok',
      text: `«${input.profile}» profili Kit tarayıcısına yüklendi (${count} çerez; ${input.domains.join(', ')}). Çerez değerleri sende değil; computer_navigate ile siteye git. Oturum Kit tarayıcısı kapanınca silinir.`,
    };
  } catch (error) {
    // Kits sunucusunun hata metni sabittir (çerez yansıtmaz); yine de yalnız ilk satır.
    const message = error instanceof Error ? error.message : '';
    return {
      status: 'failed',
      text: `Oturum Kit tarayıcısına yüklenemedi: ${message.split('\n')[0].slice(0, 200) || 'bilinmeyen hata'}. Önce Kit bilgisayarını başlat ve tarayıcı iznini aç.`,
    };
  }
}
