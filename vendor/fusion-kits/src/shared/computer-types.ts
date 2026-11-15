import { z } from 'zod';
import { sessionStateSchema } from './fusion-profile.js';
export const computerPermissionsSchema = z
  .object({
    enabled: z.boolean(),
    browser: z.boolean(),
    files: z.boolean(),
    shell: z.boolean(),
  })
  .strict();
export type ComputerPermissions = z.infer<typeof computerPermissionsSchema>;
export interface ComputerAudit {
  id: string;
  action: string;
  actor: 'owner' | 'agent';
  outcome: 'pending' | 'succeeded' | 'failed';
  createdAt: number;
}
export interface ComputerControl {
  holder: 'bot' | 'human';
  requested: boolean;
  transitioning: boolean;
  resumeSnapshotRequired: boolean;
  request?: { id: string; status: string };
}
export interface ComputerStatus {
  configured: boolean;
  /** Yerel (Docker'sız) bilgisayar denetçisi kullanılıyor. */
  local?: boolean;
  state: 'not_configured' | 'stopped' | 'running' | 'unavailable';
  permissions: ComputerPermissions;
  audit: ComputerAudit[];
  control?: ComputerControl;
  error?: string;
}
const path = z
  .string()
  .max(1024)
  .refine(
    (p) =>
      !p.startsWith('/') &&
      !p.includes('\\') &&
      !p.includes('\0') &&
      !p.split('/').some((s) => s === '..'),
    'Üst dizine çıkmayan, göreli bir çalışma alanı yolu kullan.',
  );
const empty = z.object({}).strict();
const ref = {
  ref: z.string().min(1).max(100),
  snapshotId: z.number().int().nonnegative(),
};
export const computerInputs = {
  navigate: z
    .object({
      url: z
        .string()
        .url()
        .max(2048)
        .refine(
          (s) =>
            ['http:', 'https:'].includes(new URL(s).protocol) &&
            !new URL(s).username &&
            !new URL(s).password,
        ),
    })
    .strict(),
  read: empty,
  snapshot: empty,
  screenshot: empty,
  click: z.object(ref).strict(),
  type: z
    .object({
      ...ref,
      text: z.string().max(16000),
      submit: z.boolean().optional(),
    })
    .strict(),
  key: z.object({ key: z.string().min(1).max(100) }).strict(),
  scroll: z
    .object({ deltaY: z.number().finite().min(-10000).max(10000) })
    .strict(),
  files_list: z.object({ path: path.default('') }).strict(),
  files_read: z.object({ path: path.refine((p) => p.length > 0) }).strict(),
  files_write: z
    .object({
      path: path.refine((p) => p.length > 0),
      contents: z.string().max(100000),
      append: z.boolean().optional(),
    })
    .strict(),
  exec: z
    .object({
      command: z.string().trim().min(1).max(8000),
      timeoutMs: z.number().int().min(1000).max(60000).default(30000),
    })
    .strict(),
  /** Fusion profilini Kit tarayıcısına bellek içi yükle (P-023). Yalnız sahip (Fusion
   * onayından gelen istemci) çağırır; ajan araçlarına girmez. */
  session_load: z
    .object({
      profile: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/),
      domains: z.array(z.string().min(1).max(253)).min(1).max(20),
      state: sessionStateSchema,
    })
    .strict(),
  session_clear: empty,
  human_click: z
    .object({
      x: z.number().finite().min(0).max(16000),
      y: z.number().finite().min(0).max(16000),
    })
    .strict(),
  human_type: z.object({ text: z.string().max(16000) }).strict(),
  human_key: z.object({ key: z.string().min(1).max(100) }).strict(),
  human_scroll: z
    .object({ deltaY: z.number().finite().min(-10000).max(10000) })
    .strict(),
};
export type ComputerAction = keyof typeof computerInputs;
/** Yalnız sahibin çağırabileceği eylemler: ajan araç listesine girmez. */
export const isOwnerOnlyAction = (action: string) =>
  action.startsWith('human_') || action.startsWith('session_');
