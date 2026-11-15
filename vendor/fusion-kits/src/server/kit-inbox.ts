import { z } from 'zod';
import type { Conversation, Dot, Task } from '../shared/types.js';
import type { Store } from './store.js';
import type { WorkspaceStore } from './workspace.js';

/**
 * Fusion → Kit gelen kutusu (P-063).
 *
 * Fusion (CLI aracı, masaüstü RPC'si ya da `fusion kit gonder`) bir Kit'e serbest mesaj
 * ya da görev bırakır. Teslim, Kit'in "Fusion gelen kutusu" sohbetine bağlı kalıcı bir
 * görev olarak kuyruğa girer; Kit onu kendi sırası gelince kendi sohbetinde işler.
 * Zamanlanmış teslimle (`scheduled-delivery.ts`) aynı yürütme yolu kullanılır; yeni
 * bir çalışma biçimi açılmaz. Makbuz "kuyruğa alındı" demektir, "yapıldı" değil.
 */
export const INBOX_TITLE = 'Fusion gelen kutusu';
/** Kit'in bu mesajın Fusion'dan geldiğini anlaması için istem başına konan işaret. */
export const INBOX_PREFIX = '[Fusion]';
/** Fusion'a dönen liste en fazla bu kadar gelen kutusu kaydı taşır. */
export const INBOX_LIST_LIMIT = 20;
const TITLE_LIMIT = 120;
const RESULT_EXCERPT = 2000;

export const inboxSchema = z
  .object({
    text: z
      .string()
      .min(3)
      .max(4000)
      .refine((value) => value.trim().length >= 3),
    title: z.string().trim().min(1).max(TITLE_LIMIT).optional(),
    kind: z.enum(['message', 'task']).default('task'),
  })
  .strict();
export type InboxInput = z.infer<typeof inboxSchema>;

export interface KitSummary {
  id: string;
  name: string;
  character: string | null;
  fusionAllowed: boolean;
  researchAllowed: boolean;
  inboxThreadId: string | null;
}
export interface InboxReceipt {
  kitId: string;
  threadId: string;
  taskId: string;
  status: 'queued';
}
export interface InboxItem {
  taskId: string;
  title: string;
  kind: 'message' | 'task';
  status: Task['status'];
  createdAt: number;
  updatedAt: number;
  error: string | null;
}
export interface InboxDetail extends InboxItem {
  prompt: string;
  result: string | null;
  events: string[];
}

export class KitInboxError extends Error {
  constructor(
    message: string,
    readonly status: 400 | 403 | 404 | 409 | 503 = 409,
  ) {
    super(message);
  }
}

/** Kit kimliği ya da adı (büyük/küçük harf duyarsız) ile tek Kit çöz. */
export function resolveKit(workspace: WorkspaceStore, reference: string): Dot {
  const wanted = reference.trim();
  if (!wanted) throw new KitInboxError('Bir Kit adı ya da kimliği gir.', 400);
  const dots = workspace.dots();
  const byId = dots.find((dot) => dot.id === wanted);
  if (byId) return byId;
  const byName = dots.filter((dot) => sameName(dot.name, wanted));
  if (byName.length === 1) return byName[0];
  if (byName.length > 1)
    throw new KitInboxError(
      'Aynı adda birden çok Kit var; kimliğiyle seç.',
      409,
    );
  throw new KitInboxError('Kit bulunamadı.', 404);
}

/** "Kit" ↔ "KIT" ↔ "kit": Türkçe I/ı tuzağına düşmeden iki küçültmeyle karşılaştır. */
function sameName(left: string, right: string): boolean {
  const forms = (value: string) => {
    const trimmed = value.trim();
    return new Set([trimmed.toLowerCase(), trimmed.toLocaleLowerCase('tr')]);
  };
  const candidates = forms(right);
  return [...forms(left)].some((form) => candidates.has(form));
}

export function inboxThread(
  workspace: WorkspaceStore,
  dotId: string,
): Conversation | undefined {
  return workspace
    .conversations()
    .find((thread) => thread.dotId === dotId && thread.title === INBOX_TITLE);
}

export function kitSummaries(workspace: WorkspaceStore): KitSummary[] {
  return workspace.dots().map((dot) => ({
    id: dot.id,
    name: dot.name,
    character: dot.character ?? null,
    fusionAllowed: dot.fusionAllowed === true,
    researchAllowed: dot.researchAllowed,
    inboxThreadId: inboxThread(workspace, dot.id)?.id ?? null,
  }));
}

/** Kit'in göreceği istem: kaynağı ve türü açıkça söyler, metni olduğu gibi taşır. */
export function inboxPrompt(input: InboxInput): string {
  const label =
    input.kind === 'message' ? "Fusion'dan mesaj" : "Fusion'dan görev";
  const heading = input.title ? `${label} — ${input.title}` : label;
  return `${INBOX_PREFIX} ${heading}\n\n${input.text.trim()}`;
}

function parsePrompt(prompt: string): {
  title: string;
  kind: InboxItem['kind'];
} {
  const firstLine = prompt.split('\n', 1)[0] ?? '';
  const kind: InboxItem['kind'] = firstLine.includes("Fusion'dan mesaj")
    ? 'message'
    : 'task';
  const separator = firstLine.indexOf(' — ');
  const title =
    separator >= 0
      ? firstLine.slice(separator + 3).trim()
      : (prompt.slice(firstLine.length).trim().split('\n', 1)[0] ?? '');
  return { title: title.slice(0, TITLE_LIMIT), kind };
}

export type CreateConversation = (
  dotId: string,
  title: string,
) => Promise<Conversation>;

/**
 * Teslimi Kit'in gelen kutusu sohbetine bağlı kalıcı görev olarak kuyruğa al.
 *
 * İzin kapıları zamanlanmış teslimle aynıdır: çalışma alanı duraklatılmışsa ya da görev
 * yürütme izni kapalıysa reddedilir; Kit'in Fusion izni (`fusionAllowed`) kapalıysa
 * Fusion o Kit'e yazamaz. Kit'in izinleri Kit ayarlarından değişir, bu uçtan değil.
 */
export async function deliverToKit(
  store: Store,
  workspace: WorkspaceStore,
  createConversation: CreateConversation,
  dot: Dot,
  request: InboxInput,
): Promise<InboxReceipt> {
  const input = inboxSchema.parse(request);
  assertPermitted(store, dot);
  const thread =
    inboxThread(workspace, dot.id) ??
    (await createConversation(dot.id, INBOX_TITLE));
  if (thread.dotId !== dot.id)
    throw new KitInboxError('Gelen kutusu sohbeti bu Kit’e ait değil.', 409);
  // Kuyruk ve sohbet bağı ayrı yazımlardır; ikinci düşerse görevi sahipsiz bırakma.
  const task = store.createTask(inboxPrompt(input));
  try {
    workspace.bindTask(task.id, thread.id);
  } catch (error) {
    store.action(task.id, 'cancel');
    throw error;
  }
  assertPermitted(store, dot);
  store.event(task.id, null, 'Fusion gelen kutusundan teslim edildi.');
  return {
    kitId: dot.id,
    threadId: thread.id,
    taskId: task.id,
    status: 'queued',
  };
}

function assertPermitted(store: Store, dot: Dot): void {
  const settings = store.settings();
  if (settings.paused || !settings.researchAllowed)
    throw new KitInboxError(
      settings.paused
        ? 'Çalışma alanı duraklatılmış; Kits ana ekranından sürdür.'
        : 'Görev yürütme izni kapalı; Kits > Çalışma alanı ayarları > Görev yürütme iznini aç.',
      403,
    );
  if (!dot.fusionAllowed)
    throw new KitInboxError(
      "Bu Kit'in Fusion izni kapalı; Kit'i düzenle > Fusion iznini aç.",
      403,
    );
}

export function inboxItems(
  store: Store,
  workspace: WorkspaceStore,
  dot: Dot,
  limit = INBOX_LIST_LIMIT,
): InboxItem[] {
  const thread = inboxThread(workspace, dot.id);
  if (!thread) return [];
  return store
    .tasks()
    .filter((task) => workspace.taskThread(task.id) === thread.id)
    .slice(0, limit)
    .map((task) => item(task));
}

function item(task: Task): InboxItem {
  const { title, kind } = parsePrompt(task.prompt);
  return {
    taskId: task.id,
    title,
    kind,
    status: task.status,
    createdAt: task.createdAt,
    updatedAt: task.updatedAt,
    error: task.error,
  };
}

/** Yalnız bu Kit'in gelen kutusuna bağlı görevin ayrıntısı; başkası `undefined`. */
export function inboxDetail(
  store: Store,
  workspace: WorkspaceStore,
  dot: Dot,
  taskId: string,
): InboxDetail | undefined {
  const thread = inboxThread(workspace, dot.id);
  if (!thread || workspace.taskThread(taskId) !== thread.id) return undefined;
  const detail = store.detail(taskId);
  if (!detail) return undefined;
  const latest = detail.runs.find((run) => run.result?.text);
  return {
    ...item(detail.task),
    prompt: detail.task.prompt,
    result: latest?.result?.text.slice(0, RESULT_EXCERPT) ?? null,
    events: detail.events.slice(-INBOX_LIST_LIMIT).map((event) => event.text),
  };
}
