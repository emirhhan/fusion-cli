import { modelReceipt } from '../../shared/fusion.js';
import { submissionReceipt } from '../../shared/submission.js';
import { createHash, randomUUID } from 'node:crypto';
import { join } from 'node:path';
import type { WorkspaceStore } from '../workspace.js';
import type { FusionConfig } from './config.js';
import {
  PROJECT_NAME,
  validateProjectPath,
  type ProjectEntry,
  type UserProjects,
} from './projects.js';
import type { FusionEvidence, FusionSnapshot } from '../../shared/fusion.js';
import { FusionSession } from './session.js';
import { processTransport } from './transport.js';

type SessionFactory = (config: FusionConfig, threadId: string) => FusionSession;
interface Active {
  session: FusionSession;
  cancel: () => void;
  questions: NonNullable<FusionSnapshot['question']>[];
}
export class FusionService {
  private active = new Map<string, Active>();
  private states = new Map<string, FusionSnapshot>();
  constructor(
    private workspace: WorkspaceStore,
    private paused: () => boolean,
    private config?: FusionConfig,
    private factory: SessionFactory = (config, thread) =>
      new FusionSession(
        processTransport(config, thread),
        config.requestTimeoutMs,
      ),
    private userProjects?: UserProjects,
    private kitsRoot = process.cwd(),
  ) {}
  get configured() {
    return !!this.config;
  }
  busy(threadId: string) {
    return this.active.has(threadId);
  }
  waiting(threadId: string) {
    return (
      this.active.has(threadId) &&
      this.states.get(threadId)?.status === 'waiting'
    );
  }
  snapshot(threadId: string): FusionSnapshot {
    this.workspace.requireThread(threadId);
    return structuredClone(
      this.states.get(threadId) ?? {
        configured: this.configured,
        root: this.config?.root,
        runId: null,
        status: 'idle',
        text: '',
        error: null,
        events: [],
        question: null,
      },
    );
  }
  private allowed(dotId: string, threadId: string) {
    this.workspace.requireThread(threadId, dotId);
    if (!this.config) throw new Error('Fusion bağlantısı yapılandırılmadı.');
    if (this.paused()) throw new Error('Fusion Kits duraklatıldı.');
    if (!this.workspace.dot(dotId)?.fusionAllowed)
      throw new Error('Bu Kit için Fusion görev izni kapalı.');
  }
  /** Seçilen proje yalnız yapılandırılmış izinli listeden gelebilir. */
  private projectConfig(project?: string): FusionConfig {
    const config = this.config!;
    if (!project) return config;
    const root = this.listProjects().find(
      (entry) => entry.name === project,
    )?.path;
    if (!root)
      throw new Error(
        `"${project}" izinli bir proje değil. Seçenekler: ${this.projects().join(', ') || 'yok'}.`,
      );
    return { ...config, root };
  }
  projects(): string[] {
    return this.listProjects().map((entry) => entry.name);
  }
  /** Sunucu yapılandırmasındakiler önce gelir ve aynı adı ekran ezemez. */
  listProjects(): ProjectEntry[] {
    const env = this.config?.projects ?? {};
    const user = this.userProjects?.fusionProjects() ?? {};
    return [
      ...Object.entries(env).map(([name, path]) => ({
        name,
        path,
        source: 'env' as const,
      })),
      ...Object.entries(user)
        .filter(([name]) => !Object.hasOwn(env, name))
        .map(([name, path]) => ({ name, path, source: 'user' as const })),
    ];
  }
  addProject(name: string, path: string): ProjectEntry {
    if (!this.config || !this.userProjects)
      throw new Error('Fusion bağlantısı yapılandırılmadı.');
    if (!PROJECT_NAME.test(name))
      throw new Error(
        'Proje adı harf, rakam, nokta, alt çizgi veya tire olmalı.',
      );
    if (Object.hasOwn(this.config.projects, name))
      throw new Error('Bu ad sunucu yapılandırmasında kullanılıyor.');
    const real = validateProjectPath(path, {
      fusionHome: this.config.home,
      kitsRoot: this.kitsRoot,
      home: this.config.userConfigHome,
    });
    this.userProjects.saveFusionProject(name, real);
    return { name, path: real, source: 'user' };
  }
  removeProject(name: string): boolean {
    return this.userProjects?.deleteFusionProject(name) ?? false;
  }
  async run(
    dotId: string,
    threadId: string,
    prompt: string,
    signal: AbortSignal,
    project?: string,
  ): Promise<FusionRunResult> {
    this.allowed(dotId, threadId);
    signal.throwIfAborted();
    if (this.active.has(threadId))
      throw new Error('Bu sohbet için bir Fusion görevi zaten çalışıyor.');
    if (this.active.size >= 8)
      throw new Error('Fusion aynı anda en fazla sekiz görev çalıştırabilir.');
    const config = this.projectConfig(project);
    const state: FusionSnapshot = {
      configured: true,
      root: config.root,
      runId: randomUUID(),
      status: 'running',
      text: '',
      error: null,
      events: [],
      question: null,
    };
    // Tamamlanmış en eski görüntüler silinir; çalışan oturumlar korunur.
    if (this.states.size >= 100) {
      const oldest = [...this.states.keys()].find((id) => !this.active.has(id));
      if (oldest) this.states.delete(oldest);
    }
    this.states.set(threadId, state);
    const session = this.factory(config, threadId);
    const cancel = () => {
      state.status = 'cancelled';
      state.question = null;
      void session.close().catch(() => {
        state.error = 'Fusion süreci kapatılamadı.';
      });
    };
    const questions: NonNullable<FusionSnapshot['question']>[] = [];
    this.active.set(threadId, { session, cancel, questions });
    signal.addEventListener('abort', cancel, { once: true });
    const watcher = setInterval(() => {
      try {
        this.allowed(dotId, threadId);
      } catch {
        cancel();
      }
    }, 100);
    session.onEvent((data) => {
      if (state.status === 'cancelled') return;
      const hasModelScope =
        (typeof data.session_id !== 'string' || data.session_id === threadId) &&
        (typeof data.turn_id !== 'string' ||
          data.turn_id.startsWith(`${state.runId}:`));
      const receiptModel = hasModelScope ? modelReceipt(data) : null;
      if (receiptModel) {
        const receipts = state.modelReceipts ?? [];
        state.modelReceipts = [
          ...receipts.filter(
            (entry) =>
              !receiptModel.callId || entry.callId !== receiptModel.callId,
          ),
          receiptModel,
        ].slice(-20);
      }
      if (data.olay === 'GonderimMakbuzu') {
        const receipt = submissionReceipt(data);
        if (
          receipt &&
          receipt.requestId === state.runId &&
          receipt.sessionId === threadId
        )
          state.receipt = receipt;
      }
      if (typeof data.olay === 'string') {
        state.events.push(data.olay.slice(0, 120));
        state.events = state.events.slice(-20);
      }
      if (
        ['TokenReceived', 'TurnAnswered'].includes(String(data.olay)) &&
        typeof data.text === 'string'
      )
        state.text = (state.text + data.text).slice(-12000);
    });
    session.onQuestion((id, data) => {
      if (state.status === 'cancelled') return;
      if (!questions.some((question) => question.id === id))
        questions.push({ id, data });
      state.question = questions[0];
      state.status = 'waiting';
    });
    try {
      const identity = createHash('sha256').update(threadId).digest('hex');
      const started = await session.request('oturum.baslat', {
        kok: config.root,
        ev: join(config.home, identity),
        sohbet_id: threadId,
        mod: 'security',
        kip: 'kod',
        motor: 'agent',
      });
      if (started.ok !== true)
        throw new Error(
          typeof started.metin === 'string'
            ? started.metin
            : 'Fusion oturumu açılamadı.',
        );
      this.allowed(dotId, threadId);
      signal.throwIfAborted();
      const result = await session.request('tur.calistir', {
        gorev: prompt,
        gonderim_id: state.runId,
      });
      signal.throwIfAborted();
      const receipt = submissionReceipt(result.makbuz);
      if (
        receipt &&
        receipt.requestId === state.runId &&
        receipt.sessionId === threadId
      )
        state.receipt = receipt;
      if (typeof result.ok !== 'boolean' || typeof result.metin !== 'string')
        throw new Error('Fusion sonucu protokol sözleşmesine uymuyor.');
      state.status = result.ok ? 'completed' : 'failed';
      state.text = result.metin.slice(-12000);
      state.error = result.ok ? null : state.text;
      const evidence = parseEvidence(result.kanit);
      state.evidence = evidence;
      return {
        ok: result.ok,
        text: result.metin,
        evidence,
        verification: describeEvidence(evidence),
      };
    } catch (error) {
      if (state.status !== 'cancelled') {
        state.status = 'failed';
        state.error =
          error instanceof Error ? error.message : 'Fusion görevi başarısız.';
      }
      throw error;
    } finally {
      clearInterval(watcher);
      signal.removeEventListener('abort', cancel);
      state.question = null;
      await session.close();
      this.active.delete(threadId);
    }
  }
  reply(
    threadId: string,
    runId: string,
    id: string,
    answer: Record<string, unknown>,
  ) {
    const thread = this.workspace.requireThread(threadId);
    this.allowed(thread.dotId, threadId);
    const state = this.states.get(threadId);
    const active = this.active.get(threadId);
    if (!active || !state || state.runId !== runId || state.question?.id !== id)
      throw new Error('Fusion sorusu veya görev kimliği artık geçerli değil.');
    const question = state.question.data;
    if (question.tur === 'onay') {
      if (
        !['once', 'session', 'deny'].includes(String(answer.secim)) ||
        (question.tehlike && answer.secim === 'session')
      )
        throw new Error('Fusion onay seçimi geçersiz.');
      active.session.reply(id, { secim: answer.secim });
    } else if (
      question.tur === 'soru' &&
      typeof answer.metin === 'string' &&
      answer.metin.trim() &&
      answer.metin.length <= 4000
    ) {
      active.session.reply(id, { metin: answer.metin });
    } else throw new Error('Fusion soru cevabı geçersiz.');
    active.questions.shift();
    state.question = active.questions[0] ?? null;
    state.status = state.question ? 'waiting' : 'running';
  }
  cancel(threadId: string, runId: string) {
    this.workspace.requireThread(threadId);
    if (
      this.states.get(threadId)?.runId !== runId ||
      !this.active.has(threadId)
    )
      throw new Error('Fusion görevi artık çalışmıyor.');
    this.active.get(threadId)!.cancel();
  }
  async stop() {
    await Promise.all(
      [...this.active.values()].map(async (entry) => {
        entry.cancel();
        await entry.session.close();
      }),
    );
  }
}

export interface FusionRunResult {
  ok: boolean;
  text: string;
  evidence: FusionEvidence | null;
  /** Modelin göreceği tek satırlık doğrulama özeti; kanıtsız iş "tamam" sayılmaz. */
  verification: string;
}

const strings = (value: unknown, limit: number): string[] | null =>
  Array.isArray(value) && value.every((item) => typeof item === 'string')
    ? (value as string[]).slice(0, limit)
    : null;

/** Fusion `kanit` alanını doğrula; sözleşmeye uymayan alan kanıt sayılmaz. */
export function parseEvidence(value: unknown): FusionEvidence | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (data.schema_version !== undefined && data.schema_version !== 1)
    return null;
  const changed = strings(data.degisen, 50);
  const problems = strings(data.sorunlar, 10);
  if (
    !(data.dogrulandi === null || typeof data.dogrulandi === 'boolean') ||
    typeof data.engelliyor !== 'boolean' ||
    typeof data.yanlis_iddia !== 'boolean' ||
    !changed ||
    !problems
  )
    return null;
  return {
    verified: data.dogrulandi,
    blocking: data.engelliyor,
    falseClaim: data.yanlis_iddia,
    changed,
    problems,
  };
}

export function describeEvidence(evidence: FusionEvidence | null): string {
  if (!evidence)
    return 'DOĞRULAMA: Fusion kanıt bildirmedi; sonucu doğrulanmış sayma.';
  if (evidence.falseClaim)
    return 'DOĞRULAMA: Fusion kanıtsız başarı iddia etti; iş doğrulanmadı.';
  if (evidence.blocking || evidence.problems.length)
    return `DOĞRULAMA: doğrulanmadı — engelleyen sorun var${
      evidence.problems.length ? `: ${evidence.problems.join('; ')}` : ''
    }.`;
  if (evidence.verified === true)
    return `DOĞRULAMA: doğrulandı (${evidence.changed.length} dosya değişti, test/çalıştırma kanıtı var).`;
  if (evidence.verified === false)
    return `DOĞRULAMA: doğrulanmadı — ${evidence.changed.length} dosya değişti ama son değişiklikten sonra çalışan bir kanıt yok. Kullanıcıya "tamamlandı" deme.`;
  if (evidence.changed.length)
    return `DOĞRULAMA: ${evidence.changed.length} dosya değişti; doğrulama durumu bilinmiyor. Kullanıcıya "tamamlandı" deme.`;
  return 'DOĞRULAMA: dosya değişikliği yok.';
}
