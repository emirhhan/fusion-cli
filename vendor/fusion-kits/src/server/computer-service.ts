import { createHmac } from 'node:crypto';
import { z } from 'zod';
import {
  computerInputs,
  computerPermissionsSchema,
  type ComputerAction,
  type ComputerControl,
  type ComputerStatus,
} from '../shared/computer-types.js';
import type { WorkspaceStore } from './workspace.js';
import type { PlatformConfig } from './platform-config.js';
const stateSchema = z.object({
  botId: z.string(),
  container: z.string(),
  status: z.string(),
  port: z.number().int().min(1024).max(65535).optional(),
  url: z.string().optional(),
});
const controlSchema = z.object({
  holder: z.enum(['bot', 'human']),
  requested: z.boolean(),
  transitioning: z.boolean(),
  resumeSnapshotRequired: z.boolean(),
  request: z.object({ id: z.string(), status: z.string() }).optional(),
});
/** İzin değişikliğinin uçuştaki bilgisayar çağrısını kesme sıklığı. */
const PERMISSION_WATCH_MS = 50;
/** Bu kadar sessizlikten sonra gelen kare yeni bir izleme oturumu sayılır ve denetime yazılır. */
export const WATCH_AUDIT_GAP_MS = 30_000;
export class ComputerService {
  /** Kit başına son izleme karesinin anı (denetim izini oturum başına bir satırda tutar). */
  private lastFrameAt = new Map<string, number>();
  constructor(
    private workspace: WorkspaceStore,
    private config: PlatformConfig,
    private paused: () => boolean,
    private transport: typeof fetch = fetch,
    private deadlineMs = 70000,
  ) {}
  get configured() {
    return !!(
      this.config.computerSupervisorUrl?.trim() &&
      this.config.computerSupervisorToken?.trim() &&
      this.config.computerToken?.trim()
    );
  }
  private token(id: string) {
    return createHmac('sha256', this.config.computerToken!.trim())
      .update(`opendots-computer:${id}`)
      .digest('hex');
  }
  private requireDot(id: string) {
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(id) || !this.workspace.dot(id))
      throw new Error('Kit bulunamadı.');
  }
  private allowed(
    id: string,
    kind: 'browser' | 'files' | 'shell' | undefined,
    actor: 'agent' | 'owner',
  ) {
    this.requireDot(id);
    if (!this.configured)
      throw new Error('Bilgisayar hizmeti yapılandırılmadı.');
    const policy = this.workspace.computers.permissions(id);
    if (!policy.enabled || (kind && !policy[kind]))
      throw new Error('Bilgisayar izni kapalı.');
    if (actor === 'agent' && this.paused())
      throw new Error('Kit’ler duraklatıldı.');
  }
  private async json(
    url: string,
    token: string,
    body: unknown | undefined,
    signal?: AbortSignal,
    dotId?: string,
  ): Promise<unknown> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.deadlineMs);
    const combined = signal
      ? AbortSignal.any([signal, controller.signal])
      : controller.signal;
    try {
      const response = await this.transport(url, {
        method: body === undefined ? 'GET' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          ...(dotId ? { 'x-openbot-bot-id': dotId } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        redirect: 'error',
        signal: combined,
      });
      if (response.status === 409)
        throw new Error(
          'Bilgisayar hizmeti HTTP 409 döndürdü: yeniden denemeden önce tarayıcıyı computer_snapshot ile yenile. Kontrol sahipteyse bırakmasını bekle; devralmayı atlatma.',
        );
      if (!response.ok)
        throw new Error(`Bilgisayar hizmeti HTTP ${response.status} döndürdü.`);
      if (!response.body)
        throw new Error('Bilgisayar hizmeti boş yanıt döndürdü.');
      const reader = response.body.getReader();
      let size = 0;
      const chunks: Uint8Array[] = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 4_000_000) {
          await reader.cancel();
          throw new Error('Bilgisayar yanıtı boyut sınırını aştı.');
        }
        chunks.push(value);
      }
      // Infrastructure secrets must never leave the gateway even if an upstream response reflects one.
      let text = Buffer.concat(chunks).toString('utf8');
      for (const secret of [
        token,
        this.config.computerToken?.trim(),
        this.config.computerSupervisorToken?.trim(),
      ])
        if (secret) text = text.split(secret).join('[redacted]');
      return JSON.parse(text);
    } catch (error) {
      if (combined.aborted)
        throw new Error(
          'Bilgisayar isteği iptal edildi veya zaman aşımına uğradı.',
          {
            cause: error,
          },
        );
      if (
        error instanceof Error &&
        /^Bilgisayar (hizmeti (HTTP|boş)|yanıtı boyut)/.test(error.message)
      )
        throw error;
      throw new Error(
        'Bilgisayar hizmeti kullanılamıyor veya geçersiz yanıt döndürdü.',
        { cause: error },
      );
    } finally {
      clearTimeout(timeout);
    }
  }
  private supervisor(path: string, body?: unknown, signal?: AbortSignal) {
    return this.json(
      `${this.config.computerSupervisorUrl!.replace(/\/$/, '')}${path}`,
      this.config.computerSupervisorToken!.trim(),
      body,
      signal,
    );
  }
  private endpoint(id: string, raw: unknown) {
    const state = stateSchema.parse(raw);
    const ns = this.config.computerNamespace ?? 'opendots';
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(ns))
      throw new Error('Geçersiz bilgisayar ad alanı.');
    const expected = `${ns}-computer-${id}`;
    if (state.botId !== id || state.container !== expected)
      throw new Error('Bilgisayar kimliği eşleşmiyor.');
    const url = new URL(
      state.url ??
        (state.port
          ? `http://127.0.0.1:${state.port}`
          : `http://${expected}:4100`),
    );
    const network =
      url.hostname === expected.toLowerCase() && url.port === '4100';
    const local =
      url.hostname === '127.0.0.1' &&
      !!state.port &&
      url.port === String(state.port) &&
      new URL(this.config.computerSupervisorUrl!).hostname === '127.0.0.1';
    if (
      url.protocol !== 'http:' ||
      url.username ||
      url.password ||
      url.pathname !== '/' ||
      url.search ||
      url.hash ||
      (!network && !local)
    )
      throw new Error('Bilgisayar uç noktası bu Kit’e bağlı değil.');
    return url.origin;
  }
  private async existing(id: string, signal?: AbortSignal) {
    const listing = z
      .object({ computers: z.array(stateSchema) })
      .parse(await this.supervisor('/computers', undefined, signal));
    return listing.computers.find((c) => c.botId === id);
  }
  private async running(id: string, signal?: AbortSignal) {
    const state = await this.existing(id, signal);
    if (!state || state.status !== 'running')
      throw new Error('Önce bu Kit’in bilgisayarını başlat.');
    return this.endpoint(id, state);
  }
  async status(id: string): Promise<ComputerStatus> {
    this.requireDot(id);
    const base = {
      configured: this.configured,
      ...(this.config.computerLocal ? { local: true } : {}),
      permissions: this.workspace.computers.permissions(id),
      audit: this.workspace.computers.audit(id),
    };
    if (!this.configured) return { ...base, state: 'not_configured' };
    try {
      const state = await this.existing(id);
      if (!state || state.status !== 'running')
        return { ...base, state: 'stopped' };
      const url = this.endpoint(id, state);
      const control = controlSchema.parse(
        await this.json(
          `${url}/control`,
          this.token(id),
          undefined,
          undefined,
          id,
        ),
      );
      return { ...base, state: 'running', control };
    } catch {
      return {
        ...base,
        state: 'unavailable',
        error:
          'Bilgisayar hizmeti kullanılamıyor. Denetçi yapılandırmasını ve bağlantıyı kontrol et.',
      };
    }
  }
  private async audited<T>(
    id: string,
    action: string,
    actor: 'owner' | 'agent',
    fn: () => Promise<T>,
  ): Promise<T> {
    this.requireDot(id);
    const receipt = this.workspace.computers.begin(id, action, actor);
    try {
      const result = await fn();
      this.workspace.computers.finish(receipt, 'succeeded');
      return result;
    } catch (error) {
      this.workspace.computers.finish(receipt, 'failed');
      throw error;
    }
  }
  async permissions(id: string, input: unknown) {
    const patch = computerPermissionsSchema.partial().parse(input);
    await this.audited(id, 'permissions', 'owner', async () =>
      this.workspace.computers.patch(id, patch),
    );
    return this.status(id);
  }
  async start(id: string) {
    await this.audited(id, 'start', 'owner', async () => {
      this.allowed(id, undefined, 'owner');
      this.endpoint(id, await this.supervisor(`/computers/${id}/ensure`, {}));
    });
    return this.status(id);
  }
  async stop(id: string) {
    await this.audited(id, 'stop', 'owner', async () => {
      if (!this.configured)
        throw new Error('Bilgisayar hizmeti yapılandırılmadı.');
      await this.supervisor(`/computers/${id}/stop`, {});
    });
    return this.status(id);
  }
  async control(id: string, verb: 'take' | 'release') {
    await this.audited(id, verb, 'owner', async () => {
      if (!this.configured)
        throw new Error('Bilgisayar hizmeti yapılandırılmadı.');
      if (verb === 'take') this.allowed(id, 'browser', 'owner');
      const url = await this.running(id);
      if (verb === 'take') this.allowed(id, 'browser', 'owner');
      let control: ComputerControl = controlSchema.parse(
        await this.json(
          `${url}/control`,
          this.token(id),
          undefined,
          undefined,
          id,
        ),
      );
      if (verb === 'take' && !control.request)
        control = controlSchema.parse(
          await this.json(
            `${url}/control/request`,
            this.token(id),
            { reason: 'Sahip kontrolü istedi.' },
            undefined,
            id,
          ),
        );
      if (
        verb === 'take' &&
        control.request &&
        !['waiting', 'taken'].includes(control.request.status)
      )
        control = controlSchema.parse(
          await this.json(
            `${url}/control/request`,
            this.token(id),
            { reason: 'Sahip kontrolü istedi.' },
            undefined,
            id,
          ),
        );
      if (!control.request) throw new Error('Etkin bir kontrol isteği yok.');
      await this.json(
        `${url}/control/${verb}`,
        this.token(id),
        { requestId: control.request.id },
        undefined,
        id,
      );
    });
    return this.status(id);
  }
  /**
   * Canlı izleme ve kayıt için tek ekran karesi (P-044). İzin, sahiplik ve iptal denetimi
   * `action('screenshot')` ile AYNI yoldan geçer (`gated`): uçuştaki istek izin kapanınca
   * kesilir, sonuç izin yeniden doğrulanmadan dönmez. Fark denetim kaydındadır: her kare
   * değil, bir izleme oturumunun ilk karesi (`WATCH_AUDIT_GAP_MS` sessizlikten sonra) tek
   * `watch` satırı olarak yazılır — panel saniyede bir kare çekerken etkinlik listesi
   * Kit'in gerçek işlemlerini gömmesin, ama izleme denetim izinden de kaybolmasın.
   *
   * Ölçüldü (31 Ekim, bağımsız inceleme): ilk sürüm 50 ms'lik izin izleyicisini ve sonuç
   * sonrası `allowed()` denetimini atlıyordu; izin kapanırken uçuştaki kare yine dönüyordu.
   */
  async frame(id: string, signal?: AbortSignal): Promise<unknown> {
    const now = Date.now();
    const last = this.lastFrameAt.get(id);
    this.lastFrameAt.set(id, now);
    const capture = () =>
      this.gated(id, 'browser', 'owner', signal, (url, active) =>
        this.json(`${url}/screenshot`, this.token(id), undefined, active, id),
      );
    if (last !== undefined && now - last < WATCH_AUDIT_GAP_MS) return capture();
    return this.audited(id, 'watch', 'owner', capture);
  }
  /** İzin izleyicisi + çağrı öncesi/sonrası izin denetimiyle bilgisayar çağrısı. */
  private async gated<T>(
    id: string,
    kind: 'browser' | 'files' | 'shell',
    actor: 'owner' | 'agent',
    signal: AbortSignal | undefined,
    call: (url: string, signal: AbortSignal) => Promise<T>,
  ): Promise<T> {
    this.allowed(id, kind, actor);
    const cancellation = new AbortController();
    const activeSignal = signal
      ? AbortSignal.any([signal, cancellation.signal])
      : cancellation.signal;
    const watcher = setInterval(() => {
      try {
        this.allowed(id, kind, actor);
      } catch {
        cancellation.abort();
      }
    }, PERMISSION_WATCH_MS);
    try {
      const url = await this.running(id, activeSignal);
      this.allowed(id, kind, actor);
      activeSignal.throwIfAborted();
      const result = await call(url, activeSignal);
      this.allowed(id, kind, actor);
      return result;
    } finally {
      clearInterval(watcher);
    }
  }
  async action(
    id: string,
    action: ComputerAction,
    input: unknown,
    actor: 'owner' | 'agent' = 'owner',
    signal?: AbortSignal,
  ): Promise<unknown> {
    if (!Object.hasOwn(computerInputs, action))
      throw new Error('Bilinmeyen bilgisayar işlemi.');
    const parsed = computerInputs[action].parse(input);
    return this.audited(id, action, actor, async () => {
      if (actor === 'agent' && action.startsWith('human_'))
        throw new Error('İnsan kontrolleri yalnızca sahibe aittir.');
      if (actor === 'agent' && action.startsWith('session_'))
        throw new Error(
          'Fusion oturumunu yalnız sahip (Fusion onayıyla) yükler.',
        );
      const kind =
        action === 'exec'
          ? 'shell'
          : action.startsWith('files_')
            ? 'files'
            : 'browser';
      const path = action
        .replace(/^files_/, 'files/')
        .replace(/^human_/, 'human/')
        .replace(/^session_/, 'session/');
      const result = await this.gated(id, kind, actor, signal, (url, active) =>
        this.json(
          `${url}/${path}`,
          this.token(id),
          ['read', 'screenshot'].includes(action) ? undefined : parsed,
          active,
          id,
        ),
      );
      if (action === 'exec' && result && typeof result === 'object') {
        const copy = { ...result } as Record<string, unknown>;
        delete copy.command;
        return copy;
      }
      return result;
    });
  }
}
