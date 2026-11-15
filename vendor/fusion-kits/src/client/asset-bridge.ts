import { parentOrigins } from './scheduled-delivery-bridge';
/** Host'un kalıcı dosya kimliği; yerel mutlak yol istemciye taşınmaz. */
export interface AssetReference {
  asset_id: string;
  metadata_version: 1;
  kind: string;
  mime: string | null;
  relative_path: string;
  created_at: number;
  created_by_task_id: string | null;
  parent_asset_ids: string[];
  width: number | null;
  height: number | null;
  alpha: boolean | null;
  model: string | null;
  seed: number | null;
  available: boolean;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const nullableText = (value: unknown) =>
  value === null ||
  (typeof value === 'string' && value.length > 0 && value.length <= 256);
const dimension = (value: unknown) =>
  value === null ||
  (typeof value === 'number' && Number.isSafeInteger(value) && value > 0);
export function parseAssetReference(
  raw: unknown,
  expectedId: string,
): AssetReference | null {
  if (!raw || typeof raw !== 'object') return null;
  const value = raw as Record<string, unknown>;
  if (
    value.asset_id !== expectedId ||
    !UUID.test(expectedId) ||
    value.metadata_version !== 1 ||
    typeof value.kind !== 'string' ||
    !['image', 'video', 'document', 'code', 'other'].includes(value.kind) ||
    typeof value.relative_path !== 'string' ||
    !value.relative_path ||
    value.relative_path.startsWith('/') ||
    value.relative_path.includes('\\') ||
    value.relative_path.split('/').includes('..') ||
    /^[A-Za-z]:/.test(value.relative_path) ||
    typeof value.created_at !== 'number' ||
    !Number.isFinite(value.created_at) ||
    typeof value.available !== 'boolean'
  )
    return null;
  if (
    !nullableText(value.mime) ||
    !nullableText(value.created_by_task_id) ||
    !nullableText(value.model) ||
    !dimension(value.width) ||
    !dimension(value.height) ||
    (value.alpha !== null && typeof value.alpha !== 'boolean') ||
    (value.seed !== null &&
      (typeof value.seed !== 'number' || !Number.isSafeInteger(value.seed)))
  )
    return null;
  const parents = value.parent_asset_ids;
  if (
    !Array.isArray(parents) ||
    parents.length > 32 ||
    parents.some(
      (parent) =>
        typeof parent !== 'string' ||
        !UUID.test(parent) ||
        parent === expectedId,
    ) ||
    new Set(parents).size !== parents.length
  )
    return null;
  return {
    asset_id: expectedId,
    metadata_version: 1,
    kind: value.kind,
    mime: value.mime as string | null,
    relative_path: value.relative_path,
    created_at: value.created_at,
    created_by_task_id: value.created_by_task_id as string | null,
    parent_asset_ids: [...parents] as string[],
    width: value.width as number | null,
    height: value.height as number | null,
    alpha: value.alpha as boolean | null,
    model: value.model as string | null,
    seed: value.seed as number | null,
    available: value.available,
  };
}

export interface AssetView {
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
export type AssetApi = <T>(
  path: string,
  method?: string,
  body?: unknown,
  signal?: AbortSignal,
) => Promise<T>;
export type AssetResolution =
  | { status: 'ready' | 'missing'; asset: AssetReference }
  | { status: 'unavailable'; message: string };
/** Politika okuması, host yanıtı ve kapanış tek süre/sahiplik bütçesini paylaşır. */
function requestHostAsset<T>(
  view: AssetView,
  api: AssetApi,
  request: Record<string, unknown>,
  parse: (data: Record<string, unknown>) => T | null,
  options: {
    nonce?: () => string;
    timeoutMs?: number;
    signal?: AbortSignal;
  } = {},
): Promise<HostAssetResult<T>> {
  if (view.parent === view.self)
    return Promise.resolve({
      status: 'unavailable',
      message: 'Dosya için Fusion uygulaması bağlantısı gerekli.',
    });
  const nonce = (options.nonce ?? (() => crypto.randomUUID()))();
  const timeout = options.timeoutMs ?? 20000;
  if (
    !/^[A-Za-z0-9_-]{1,100}$/.test(nonce) ||
    !Number.isFinite(timeout) ||
    timeout < 1 ||
    timeout > 60000
  )
    return Promise.resolve({
      status: 'unavailable',
      message: 'Dosya isteği geçersiz.',
    });
  return new Promise((resolve) => {
    let done = false;
    let origins: string[] = [];
    const policy = new AbortController();
    const finish = (result: HostAssetResult<T>) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      view.removeEventListener('message', receive);
      options.signal?.removeEventListener('abort', abort);
      policy.abort();
      resolve(result);
    };
    const receive = (event: MessageEvent) => {
      if (event.source !== view.parent || !origins.includes(event.origin))
        return;
      const data = event.data as Record<string, unknown> | null;
      if (
        !data ||
        typeof data !== 'object' ||
        data.type !== 'fusion-asset-result' ||
        data.nonce !== nonce
      )
        return;
      const value = data.ok === true ? parse(data) : null;
      finish(
        value !== null
          ? { status: 'ready', value }
          : {
              status: 'unavailable',
              message: 'Dosya kimliği bu kapsamda doğrulanamadı.',
            },
      );
    };
    const abort = () =>
      finish({ status: 'unavailable', message: 'Dosya gözlemi kapatıldı.' });
    const timer = setTimeout(
      () =>
        finish({
          status: 'unavailable',
          message: 'Fusion dosya yanıtı süre içinde doğrulanamadı.',
        }),
      timeout,
    );
    options.signal?.addEventListener('abort', abort, { once: true });
    if (options.signal?.aborted) {
      abort();
      return;
    }
    void parentOrigins(<T>(path: string, method?: string, body?: unknown) =>
      api<T>(path, method, body, policy.signal),
    )
      .then((allowed) => {
        if (done) return;
        origins = allowed;
        if (!origins.length) {
          finish({
            status: 'unavailable',
            message: 'İzinli Fusion host bağlantısı yok.',
          });
          return;
        }
        view.addEventListener('message', receive);
        for (const origin of origins)
          view.parent.postMessage({ ...request, nonce }, origin);
      })
      .catch(() =>
        finish({
          status: 'unavailable',
          message: 'Fusion host politikası alınamadı.',
        }),
      );
  });
}

export interface AssetRequestOptions {
  nonce?: () => string;
  timeoutMs?: number;
  signal?: AbortSignal;
}
export type HostAssetResult<T> =
  { status: 'ready'; value: T } | { status: 'unavailable'; message: string };
export type AssetCursor = [number, string] | null;
export interface AssetPage {
  items: AssetReference[];
  next_cursor: AssetCursor;
}
export interface AssetPreview {
  asset_id: string;
  data_url: string;
  width: number;
  height: number;
  sha256: string;
}
function validCursor(value: unknown): value is AssetCursor {
  return (
    value === null ||
    (Array.isArray(value) &&
      value.length === 2 &&
      typeof value[0] === 'number' &&
      Number.isFinite(value[0]) &&
      value[0] >= 0 &&
      typeof value[1] === 'string' &&
      UUID.test(value[1]))
  );
}
export async function requestAssetReference(
  view: AssetView,
  api: AssetApi,
  assetId: string,
  options: AssetRequestOptions = {},
): Promise<AssetResolution> {
  if (!UUID.test(assetId))
    return { status: 'unavailable', message: 'Dosya kimliği geçersiz.' };
  const result = await requestHostAsset(
    view,
    api,
    { type: 'fusion-asset-resolve', asset_id: assetId },
    (data) => parseAssetReference(data.asset, assetId),
    options,
  );
  return result.status === 'ready'
    ? {
        status: result.value.available ? 'ready' : 'missing',
        asset: result.value,
      }
    : result;
}
export function requestAssetPage(
  view: AssetView,
  api: AssetApi,
  cursor: AssetCursor = null,
  options: AssetRequestOptions = {},
): Promise<HostAssetResult<AssetPage>> {
  if (!validCursor(cursor))
    return Promise.resolve({
      status: 'unavailable',
      message: 'Dosya sayfa işareti geçersiz.',
    });
  return requestHostAsset(
    view,
    api,
    { type: 'fusion-asset-list', cursor },
    (data) => {
      if (
        !Array.isArray(data.items) ||
        data.items.length > 50 ||
        !validCursor(data.next_cursor)
      )
        return null;
      const items: AssetReference[] = [];
      for (const item of data.items) {
        const asset = parseAssetReference(item, item?.asset_id);
        if (!asset || items.some((old) => old.asset_id === asset.asset_id))
          return null;
        items.push(asset);
      }
      return { items, next_cursor: data.next_cursor };
    },
    options,
  );
}
export function requestAssetPreview(
  view: AssetView,
  api: AssetApi,
  assetId: string,
  options: AssetRequestOptions = {},
): Promise<HostAssetResult<AssetPreview>> {
  if (!UUID.test(assetId))
    return Promise.resolve({
      status: 'unavailable',
      message: 'Dosya kimliği geçersiz.',
    });
  return requestHostAsset(
    view,
    api,
    { type: 'fusion-asset-preview', asset_id: assetId },
    (data) => {
      if (
        data.asset_id !== assetId ||
        typeof data.data_url !== 'string' ||
        data.data_url.length > 1500022 ||
        !/^data:image\/png;base64,[A-Za-z0-9+/]+=*$/.test(data.data_url) ||
        !Number.isSafeInteger(data.width) ||
        Number(data.width) <= 0 ||
        !Number.isSafeInteger(data.height) ||
        Number(data.height) <= 0 ||
        typeof data.sha256 !== 'string' ||
        !/^[a-f0-9]{64}$/.test(data.sha256)
      )
        return null;
      return {
        asset_id: assetId,
        data_url: data.data_url,
        width: Number(data.width),
        height: Number(data.height),
        sha256: data.sha256,
      };
    },
    options,
  );
}
