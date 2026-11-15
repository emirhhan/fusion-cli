import { createHash } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { z } from 'zod';
import type { Claim } from './store.js';
import type { Store } from './store.js';
import type { WorkspaceStore } from './workspace.js';
export const deliverySchema = z
  .object({
    occurrenceId: z.string().regex(/^[a-f0-9]{64}$/),
    prompt: z
      .string()
      .min(3)
      .max(4000)
      .refine((value) => value.trim().length >= 3),
    root: z.string().min(1),
    threadId: z.string().min(1),
  })
  .strict();
export type ScheduleDeliveryInput = z.infer<typeof deliverySchema>;
export interface ScheduleDeliveryReceipt {
  occurrenceId: string;
  taskId: string;
  status: 'queued';
}
export interface StagedDelivery {
  occurrenceId: string;
  taskId: string;
  digest: string;
  prompt: string;
}
export interface DeliveryFusion {
  readonly configured: boolean;
  snapshot(threadId: string): { root?: string };
}
function validatePermission(
  store: Store,
  workspace: WorkspaceStore,
  fusion: DeliveryFusion,
  input: ScheduleDeliveryInput,
): string {
  const settings = store.settings();
  if (settings.paused || !settings.researchAllowed)
    throw new Error('Görev yürütme izni kapalı.');
  const thread = workspace.requireThread(input.threadId);
  if (!workspace.dot(thread.dotId)?.fusionAllowed || !fusion.configured)
    throw new Error('Fusion görev izni veya bağlantısı yok.');
  const configuredRoot = fusion.snapshot(thread.id).root;
  if (
    !configuredRoot ||
    realpathSync(configuredRoot) !== realpathSync(input.root)
  )
    throw new Error('Görev kökü yapılandırılmış Fusion köküyle eşleşmiyor.');
  return realpathSync(input.root);
}
/** Kalıcı sıraya teslim kanıtıdır; görevin çalıştığı veya tamamlandığı anlamına gelmez. */
export function deliverSchedule(
  store: Store,
  workspace: WorkspaceStore,
  fusion: DeliveryFusion,
  request: ScheduleDeliveryInput,
): ScheduleDeliveryReceipt {
  const input = deliverySchema.parse(request);
  const root = validatePermission(store, workspace, fusion, input);
  const digest = createHash('sha256')
    .update(JSON.stringify([input.prompt, root, input.threadId]))
    .digest('hex');
  const staged = store.stageDelivery(
    input.occurrenceId,
    digest,
    input.prompt,
    root,
    input.threadId,
  );
  workspace.bindTask(staged.taskId, input.threadId);
  validatePermission(store, workspace, fusion, input);
  return store.activateDelivery(input.occurrenceId, digest);
}

/** Runner'ın mevcut yürütücüsünden önce kabul edilmiş kapsam yeniden doğrulanır. */
export function assertScheduledExecution(
  store: Store,
  workspace: WorkspaceStore,
  fusion: DeliveryFusion,
  claim: Claim,
): void {
  const accepted = store.scheduledDelivery(claim.id);
  if (!accepted) return;
  if (
    !accepted.activated ||
    !accepted.root ||
    !accepted.threadId ||
    accepted.prompt !== claim.prompt ||
    workspace.taskThread(claim.id) !== accepted.threadId
  )
    throw new Error(
      'Kalıcı görevin kabul edilmiş kapsamı eksik veya değişmiş.',
    );
  validatePermission(store, workspace, fusion, {
    occurrenceId: accepted.occurrenceId,
    prompt: accepted.prompt,
    root: accepted.root,
    threadId: accepted.threadId,
  });
}
