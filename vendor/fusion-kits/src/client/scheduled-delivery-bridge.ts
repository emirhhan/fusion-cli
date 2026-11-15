import { kitsHostOrigins } from '../shared/host-origins';
export interface DeliveryBinding {
  readonly threadId: string;
  readonly root: string;
}
type Api = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
interface View {
  parent: Window;
  addEventListener(
    type: 'message',
    listener: (event: MessageEvent) => void,
  ): void;
  removeEventListener(
    type: 'message',
    listener: (event: MessageEvent) => void,
  ): void;
}
/** Açık kullanıcı eylemi içindir; seçim değişikliği bu fonksiyonu çağırmaz. */
export async function bindScheduledThread(
  api: Api,
  threadId: string,
  fusionAllowed: boolean,
): Promise<DeliveryBinding> {
  if (!threadId || !fusionAllowed)
    throw new Error('Fusion izni olan bir sohbet seçin.');
  const snapshot = await api<{ configured?: unknown; root?: unknown }>(
    `/conversations/${encodeURIComponent(threadId)}/fusion`,
  );
  if (
    snapshot.configured !== true ||
    typeof snapshot.root !== 'string' ||
    !snapshot.root.trim()
  )
    throw new Error('Bu sohbetin Fusion kökü yapılandırılmamış.');
  return Object.freeze({ threadId, root: snapshot.root });
}
interface Connection {
  readonly origin: string;
  readonly nonce: string;
}
function validRequest(
  data: Record<string, unknown>,
  connection: Connection | undefined,
  origin: string,
  binding: DeliveryBinding,
): data is Record<string, unknown> & { occurrenceId: string; prompt: string } {
  return (
    data.type === 'fusion-schedule-deliver' &&
    !!connection &&
    origin === connection.origin &&
    data.nonce === connection.nonce &&
    data.threadId === binding.threadId &&
    data.root === binding.root &&
    typeof data.occurrenceId === 'string' &&
    /^[a-f0-9]{64}$/.test(data.occurrenceId) &&
    typeof data.prompt === 'string'
  );
}
async function deliver(
  api: Api,
  binding: DeliveryBinding,
  occurrenceId: string,
  prompt: string,
  connection: Connection,
  current: () => boolean,
  parent: Window,
): Promise<void> {
  try {
    const receipt = await api<{
      occurrenceId?: unknown;
      taskId?: unknown;
      status?: unknown;
    }>('/scheduled-deliveries', 'POST', { occurrenceId, prompt, ...binding });
    if (
      !current() ||
      receipt.occurrenceId !== occurrenceId ||
      receipt.taskId !== `schedule-${occurrenceId}` ||
      receipt.status !== 'queued'
    )
      return;
    parent.postMessage(
      {
        type: 'fusion-schedule-receipt',
        nonce: connection.nonce,
        occurrenceId,
        taskId: receipt.taskId,
        status: 'queued',
      },
      connection.origin,
    );
  } catch {
    // Makbuz yoksa host ack veremez; kalıcı occurrence sonraki yoklamada denenir.
  }
}
export async function parentOrigins(api: Api): Promise<string[]> {
  const policy = await api<{ allowedParentOrigins?: unknown }>(
    '/host-bridge-policy',
  );
  const origins = policy.allowedParentOrigins;
  if (
    !Array.isArray(origins) ||
    !origins.every(
      (value) =>
        typeof value === 'string' && value !== 'null' && value.length > 0,
    )
  )
    throw new Error('Host teslim politikası alınamadı.');
  return origins.length ? [...kitsHostOrigins(JSON.stringify(origins))] : [];
}
function allowedMessage(
  event: MessageEvent,
  view: View,
  origins: string[],
): boolean {
  return (
    event.source === view.parent &&
    event.origin !== 'null' &&
    origins.includes(event.origin)
  );
}
export async function listenScheduledDelivery(
  view: View,
  api: Api,
  binding: DeliveryBinding,
  nonce: () => string = () => crypto.randomUUID(),
): Promise<() => void> {
  const capturedBinding = Object.freeze({ ...binding });
  const origins = await parentOrigins(api);
  let active = true;
  let connection: Connection | undefined;
  const pending = new Set<string>();
  const onMessage = (event: MessageEvent) => {
    if (!active || !allowedMessage(event, view, origins)) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'fusion-schedule-connect') {
      connection = { origin: event.origin, nonce: nonce() };
      view.parent.postMessage(
        {
          type: 'fusion-schedule-ready',
          nonce: connection.nonce,
          ...capturedBinding,
        },
        event.origin,
      );
      return;
    }
    const captured = connection;
    if (
      !validRequest(data, captured, event.origin, capturedBinding) ||
      !captured ||
      pending.has(data.occurrenceId)
    )
      return;
    const occurrenceId = data.occurrenceId;
    pending.add(occurrenceId);
    void deliver(
      api,
      capturedBinding,
      occurrenceId,
      data.prompt,
      captured,
      () => active && connection === captured,
      view.parent,
    ).finally(() => pending.delete(occurrenceId));
  };
  view.addEventListener('message', onMessage);
  return () => {
    active = false;
    connection = undefined;
    view.removeEventListener('message', onMessage);
  };
}
