import type { IstekFn } from "./akisCalistir";
import { cancelImageJob, observeImageJob, readImageJobPage } from "./imageJobClient";
import { ImageJobJournal } from "./imageJobJournal";

type Payload = Record<string, unknown>;
/** `notFound`: sunucu bu kapsamda işi tanımadığını AÇIKÇA söyledi; yalnız o zaman unutulabilir. */
export interface PendingImageJob { jobId: string; state: string; busy: boolean; stopping?: boolean; message?: string; notFound?: boolean }
export interface ImageJobControllerState { ready: boolean; error: string | null; jobs: PendingImageJob[] }
const PENDING = new Set(["accepted", "running", "recoveryRequired"]);
const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const MAX_PAGES = 20;

/** Kalıcı kimlik, kapsamlı sunucu kaydı ve yerel gözlem sahipliğinin tek sınırı. */
export class ImageJobController {
  state: ImageJobControllerState = { ready: false, error: null, jobs: [] };
  private disposed = false;
  private loading: Promise<void> | null = null;
  private operations = new Map<string, AbortController>();
  private loadingAbort = new AbortController();

  constructor(
    private readonly request: IstekFn,
    private readonly journal: ImageJobJournal,
    private readonly notify: (state: ImageJobControllerState) => void,
    private readonly createId: () => string = () => crypto.randomUUID(),
  ) {}

  initialize(): Promise<void> {
    if (this.loading) return this.loading;
    if (this.disposed) return Promise.resolve();
    const loading = this.load().finally(() => { if (this.loading === loading) this.loading = null; });
    this.loading = loading;
    return loading;
  }

  private async load(): Promise<void> {
    this.publish({ ...this.state, ready: false, error: null });
    try {
      const jobs = new Map(this.journal.read().map((jobId) => [jobId, { jobId, state: "recoveryRequired", busy: false }]));
      let cursor = "", finished = false;
      const cursors = new Set<string>();
      for (let page = 0; page < MAX_PAGES; page++) {
        const result = await readImageJobPage(this.request, cursor, this.loadingAbort.signal);
        if (this.disposed) return;
        for (const job of result.jobs) if (PENDING.has(job.state)) {
          this.journal.add(job.jobId);
          jobs.set(job.jobId, { ...job, busy: false });
        }
        if (result.next === null) { finished = true; break; }
        if (cursors.has(result.next)) throw new Error("Görsel iş listesinin sayfaları doğrulanamadı.");
        cursors.add(result.next); cursor = result.next;
      }
      if (!finished) throw new Error("Görsel iş listesi çok uzun; toparlanma tamamlanmadı.");
      this.publish({ ready: true, error: null, jobs: [...jobs.values()] });
    } catch (error) {
      this.publish({ ...this.state, ready: false, error: error instanceof Error ? error.message : "Görsel işleri okunamadı." });
    }
  }

  async start(payload: Payload): Promise<Payload> {
    if (this.disposed || !this.state.ready || this.state.jobs.length) throw new Error("Önce bekleyen görsel işlerinin durumunu kontrol et.");
    const jobId = this.createId();
    this.journal.add(jobId);
    this.publish({ ...this.state, jobs: [...this.state.jobs, { jobId, state: "accepted", busy: true }] });
    return this.execute(jobId, "start", payload);
  }

  observe(jobId: string): Promise<Payload> { return this.execute(jobId, "observe"); }
  cancel(jobId: string): Promise<Payload> { return this.execute(jobId, "cancel"); }

  /**
   * Sunucunun tanımadığı işin yerel kaydını siler. Ölçüldü (29 Ekim, U3-08): sunucuda artık
   * bulunmayan iş `recoveryRequired` kalıp yeni üretimi sonsuza dek engelliyordu. Yalnız sunucu
   * "bulunamadı" dediyse ve işlem sürmüyorsa izin verilir: canlı bir işin korumasını açmaz.
   */
  async forget(jobId: string): Promise<void> {
    const job = this.state.jobs.find((item) => item.jobId === jobId);
    if (this.disposed || !job) throw new Error("Görsel işinin sahibi değişti.");
    if (!job.notFound || job.busy) throw new Error("İş sunucuda bulunmadığı doğrulanmadan unutulamaz; önce durumunu kontrol et.");
    this.journal.remove(jobId);
    this.publish({ ...this.state, jobs: this.state.jobs.filter((item) => item.jobId !== jobId) });
  }

  private async execute(jobId: string, action: "start" | "observe" | "cancel", payload?: Payload): Promise<Payload> {
    if (this.disposed || !this.state.jobs.some((job) => job.jobId === jobId)) throw new Error("Görsel işinin sahibi değişti.");
    const previous = this.operations.get(jobId);
    if (action === "cancel" && this.state.jobs.find((job) => job.jobId === jobId)?.stopping) throw new Error("Durdurma temizliği zaten bekleniyor.");
    if (previous && action !== "cancel") throw new Error("Bu görsel işinin durumu zaten izleniyor.");
    previous?.abort();
    const owner = new AbortController();
    this.operations.set(jobId, owner);
    const owns = () => !this.disposed && this.operations.get(jobId) === owner;
    this.update(jobId, { busy: true, stopping: action === "cancel" });
    try {
      const options = { signal: owner.signal, onState: (result: Payload) => {
        if (owns()) this.update(jobId, { state: String(result.state) });
      } };
      const result = action === "cancel" ? await cancelImageJob(this.request, jobId, options)
        : await observeImageJob(this.request, jobId, { ...options, ...(action === "start" ? { start: payload } : {}) });
      if (owns()) {
        if (TERMINAL.has(String(result.state))) {
          this.journal.remove(jobId);
          this.publish({ ...this.state, jobs: this.state.jobs.filter((job) => job.jobId !== jobId) });
        } else this.update(jobId, {
          state: "recoveryRequired", message: String(result.metin ?? "İşin sonucu doğrulanamadı."),
          notFound: result.code === "job_not_found",
        });
      }
      return result;
    } catch (error) {
      if (owns()) this.update(jobId, { state: "recoveryRequired", message: error instanceof Error ? error.message : "Görsel işi doğrulanamadı." });
      throw error;
    } finally {
      if (owns()) { this.operations.delete(jobId); this.update(jobId, { busy: false, stopping: false }); }
    }
  }

  private update(jobId: string, patch: Partial<PendingImageJob>): void {
    const existing = this.state.jobs.find((job) => job.jobId === jobId);
    if (!existing) return;
    this.publish({ ...this.state, jobs: this.state.jobs.map((job) => job.jobId === jobId ? { ...job, ...patch } : job) });
  }

  private publish(state: ImageJobControllerState): void {
    if (this.disposed) return;
    this.state = state; this.notify(state);
  }

  dispose(): void {
    this.disposed = true;
    this.loadingAbort.abort();
    for (const operation of this.operations.values()) operation.abort();
    this.operations.clear();
  }
}
