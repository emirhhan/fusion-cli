import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ImageJobControllerState } from "./imageJobController";

const LABELS: Record<string, string> = { accepted: "Kabul edildi", running: "Üretiliyor", recoveryRequired: "Sonucu kontrol et", completed: "Tamamlandı", failed: "Üretilemedi", cancelled: "Durduruldu" };
export function ImageJobPanel({ state, onRecover, onRetry, onEmptyFocus }: { state: ImageJobControllerState; onRecover: (jobId: string, cancel: boolean) => void; onRetry: () => void; onEmptyFocus: () => void }) {
  const panel = useRef<HTMLElement>(null);
  const focused = useRef<HTMLElement | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    const present = new Set(state.jobs.map((job) => job.jobId));
    setExpanded((previous) => [...previous].every((id) => present.has(id)) ? previous : new Set([...previous].filter((id) => present.has(id))));
  }, [state.jobs]);
  useLayoutEffect(() => {
    if (focused.current && !focused.current.isConnected) {
      focused.current = null;
      if (document.activeElement === document.body) {
        const remaining = panel.current?.querySelector<HTMLButtonElement>(".image-create__job-actions button:not(:disabled)");
        if (remaining) remaining.focus(); else onEmptyFocus();
      }
    }
  }, [state.jobs, onEmptyFocus]);
  if (state.ready && !state.jobs.length && !state.error) return null;
  return <aside ref={panel} onFocusCapture={(event) => { if (event.target instanceof HTMLElement) focused.current = event.target; }} className="image-create__jobs" aria-label="Görsel işleri">
    <div className="image-create__jobs-heading"><strong>Görsel işleri</strong><span>Bağlantı kesilse de aynı işi takip et</span><span className="image-create__mobile-only">{state.jobs.length > 0 ? `${state.jobs.length} iş` : "İş takibi"}</span></div>
    {!state.ready && !state.error && <p role="status">Bekleyen işler kontrol ediliyor…</p>}
    {state.error && <p role="alert">{state.error} <button type="button" onClick={onRetry}>İşleri yeniden oku</button></p>}
    {state.jobs.map((job) => <div className="image-create__job" key={job.jobId} data-expanded={expanded.has(job.jobId)}>
      <div className="image-create__job-summary"><span role="status">{LABELS[job.state] ?? "Durum bilinmiyor"}</span><code title={job.jobId}>{job.jobId}</code>
        <button className="image-create__job-details-toggle image-create__mobile-only" type="button" aria-label="İş ayrıntıları" aria-expanded={expanded.has(job.jobId)} aria-controls={`image-job-detail-${job.jobId}`} onClick={() => setExpanded((previous) => { const next = new Set(previous); if (next.has(job.jobId)) next.delete(job.jobId); else next.add(job.jobId); return next; })}>{expanded.has(job.jobId) ? "Kapat" : "Ayrıntılar"}</button>
      </div>
      {job.message && <p className="image-create__job-message">{job.message}</p>}
      <div className="image-create__job-actions">
        <button aria-label={job.busy ? "İzleniyor…" : "Durumu kontrol et"} disabled={job.busy} type="button" onClick={() => onRecover(job.jobId, false)}><span className="image-create__desktop-label">{job.busy ? "İzleniyor…" : "Durumu kontrol et"}</span><span className="image-create__mobile-only">{job.busy ? "İzleniyor…" : "Kontrol et"}</span></button>
        <button aria-label={job.stopping ? "Durduruluyor…" : "Üretimi durdur"} disabled={job.stopping} type="button" onClick={() => onRecover(job.jobId, true)}><span className="image-create__desktop-label">{job.stopping ? "Durduruluyor…" : "Üretimi durdur"}</span><span className="image-create__mobile-only">{job.stopping ? "Durduruluyor…" : "Durdur"}</span></button>
      </div>
      <div className="image-create__job-detail image-create__mobile-only" id={`image-job-detail-${job.jobId}`}>
        <code>{job.jobId}</code><p>Durumu kontrol etmek aynı işi izler, yeni görsel üretmez. Durdurma temizliği bitene kadar iş kapanmış sayılmaz; sağlayıcıda oluşmuş kullanım geri alınmaz.</p>
      </div>
    </div>)}
    {state.jobs.length > 0 && <p className="image-create__job-note"><span className="image-create__desktop-label">Sonucu belirsiz işleri kontrol etmeden yeni üretim başlatılmaz. Durdurma, sağlayıcıda oluşmuş kullanımı geri almaz.</span><span className="image-create__mobile-only">Bu iş netleşmeden yeni üretim başlamaz.</span></p>}
  </aside>;
}
