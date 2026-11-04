import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { OlayAdimi } from "../protocol/olayMetni";
import { ActivityStep } from "./ActivityLine";
import "./WorkActivityPanel.css";

export interface WorkActivityEntry { id: string; step: OlayAdimi }

/** Bir turun farklı model/olay bloklarından gelen işlemlerin tek görünümü. */
export function WorkActivityPanel({ entries, onInteract }: { entries: WorkActivityEntry[]; onInteract: () => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [requested, setRequested] = useState(false);
  const selected = useRef<string | null>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  const panelId = useId();
  const many = entries.length > 2;
  const runningCount = entries.filter(entry => entry.step.basladi && !entry.step.durum).length;
  const failedCount = entries.filter(entry => entry.step.durum === "failed" || entry.step.durum === "timeout").length;
  const countLabel = `${entries.length} işlem${runningCount ? ` · ${runningCount} sürüyor` : ""}${failedCount ? ` · ${failedCount} başarısız` : ""}`;
  // İki açık satıra üçüncüsü eklenirse seçilen ayrıntı panelin içinde açık kalır.
  const open = many && (requested || expanded.size > 0);
  const previousOpen = useRef(false);
  useLayoutEffect(() => {
    if (open === previousOpen.current) return;
    previousOpen.current = open;
    const scope = open ? panel.current : wrapper.current;
    const rows = scope?.querySelectorAll<HTMLDetailsElement>("details[data-step-id]");
    const row = Array.from(rows ?? []).find(item => item.dataset.stepId === selected.current) ?? rows?.[0];
    row?.querySelector<HTMLElement>("summary")?.focus({ preventScroll: true });
  }, [open]);
  useEffect(() => {
    const element = panel.current;
    if (!open || !element) return;
    // CSS contain sınırdaki zinciri keser; kaydırılamayan kısa panelde de ana
    // sohbet kaymamalı. Native non-passive listener preventDefault'ü mümkün kılar.
    const wheel = (event: WheelEvent) => {
      event.stopPropagation();
      onInteract();
      let target = event.target instanceof Element ? event.target : null;
      let canScroll = false;
      while (target && element.contains(target)) {
        if (target instanceof HTMLElement) {
          const style = getComputedStyle(target);
          const scrollable = /auto|scroll/.test(style.overflowY) && target.scrollHeight > target.clientHeight;
          if (scrollable && ((event.deltaY < 0 && target.scrollTop > 0)
            || (event.deltaY > 0 && target.scrollTop + target.clientHeight < target.scrollHeight - 1))) canScroll = true;
        }
        if (target === element) break;
        target = target.parentElement;
      }
      if (!canScroll && event.deltaY !== 0) event.preventDefault();
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [open, onInteract]);
  if (!entries.length) return null;
  const close = () => { onInteract(); setRequested(false); setExpanded(new Set()); };
  const rows = (open ? entries : entries.slice(0, 2)).map(({ id, step }) => <ActivityStep key={id} stepId={id} adim={step}
    expanded={expanded.has(id)} onExpandedChange={next => {
      onInteract(); selected.current = id;
      setExpanded(current => { const result = new Set(current); if (next) result.add(id); else result.delete(id); return result; });
      if (many) setRequested(true);
    }} />);
  return <div className="work-activity" ref={wrapper}>
    {open ? <section ref={panel} className="work-activity-panel" aria-label="İşlem ayrıntıları" role="region" id={panelId}
      onPointerDownCapture={onInteract} onKeyDownCapture={event => {
        onInteract();
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
      }}>
      <div className="work-activity-panel__header"><span>{countLabel}</span>
        <button type="button" aria-label="İşlem panelini kapat" onClick={close}>Kapat</button></div>
      <div className="work-activity-panel__scroll" tabIndex={0} aria-label="İşlemleri kaydır"><ol className="activity__trail">{rows}</ol></div>
    </section> : <><ol className="activity__trail work-activity__preview">{rows}</ol>
      {many && <p className="work-activity__count">{countLabel} · tümünü görmek için bir satırı aç</p>}</>}
  </div>;
}
