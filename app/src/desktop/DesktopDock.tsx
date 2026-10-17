import { useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import { parseActivity, parseItems, type DesktopActivity, type DockItem, type DesktopTarget } from "./targets";
import "./desktop.css";

/** Sorgu tamamlandıktan sonra beklenir; yavaş yerel yakalamalar üst üste binmez. */
export const DOCK_POLL_MS = 2000;

export function DesktopDock({ client }: { client: ProtocolClient | null }) {
  const [collapsed, setCollapsed] = useState(false);
  const [items, setItems] = useState<DockItem[]>([]);
  const [activity, setActivity] = useState<DesktopActivity | null>(null);
  const [frame, setFrame] = useState<{ key: string; source: string } | null>(null);
  const [error, setError] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [dismissed, setDismissed] = useState("");
  const dismissedRef = useRef("");

  useEffect(() => {
    if (!client) return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const [targets, state] = await Promise.all([
          client.request("masaustu.hedefler", {}), client.request("masaustu.etkinlik", {}),
        ]);
        if (stopped) return;
        setItems([...parseItems(targets.windows), ...parseItems(targets.tabs)]);
        setError(targets.ok === true ? String(targets.native_error || targets.chrome_error || "") : String(targets.metin || targets.native_error || "Masaüstü hedefleri alınamadı."));
        const next = parseActivity(state);
        setActivity(next);
        if (!next) { setFrame(null); setPreviewError(""); }
        if (next && next.key !== dismissedRef.current) {
          setFrame((current) => current?.key === next.key ? current : null);
          try {
            const snapshot = await client.request("masaustu.onizleme", { target: next.target });
            if (stopped) return;
            if (snapshot.ok !== true || typeof snapshot.pngBase64 !== "string" || !/^[A-Za-z0-9+/]+=*$/.test(snapshot.pngBase64)) {
              throw new Error(String(snapshot.metin || "Pencere görüntüsü alınamadı."));
            }
            setFrame({ key: next.key, source: `data:image/png;base64,${snapshot.pngBase64}` });
            setPreviewError("");
          } catch (reason) {
            if (!stopped) { setFrame(null); setPreviewError(errorMessage(reason)); }
          }
        }
      } catch (reason) {
        if (!stopped) { setActivity(null); setFrame(null); setError(errorMessage(reason)); }
      } finally {
        if (!stopped) timer = window.setTimeout(() => void poll(), DOCK_POLL_MS);
      }
    };
    void poll();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [client]);

  const focus = async (target: DesktopTarget) => {
    try {
      const result = await client?.request("masaustu.odakla", { target });
      if (result?.ok !== true) throw new Error(String(result?.metin || "Hedef öne getirilemedi."));
      setError("");
    } catch (reason) { setError(errorMessage(reason)); }
  };
  if (!client) return null;
  return <aside className="desktop-dock" aria-label="Masaüstü ve sekmeler">
    <div className="desktop-dock__row">
    <button className="desktop-dock__toggle" type="button" aria-expanded={!collapsed}
      aria-label={collapsed ? "Masaüstü dock'unu aç" : "Masaüstü dock'unu daralt"}
      onClick={() => setCollapsed((current) => !current)}>Masaüstü {collapsed ? "+" : "−"}</button>
    <nav hidden={collapsed} className="desktop-dock__targets" aria-label="Açık pencereler ve sekmeler">
      {items.map((item) => <button type="button" key={`${item.target.kind}-${item.target.id}`} title={item.title}
        aria-label={`${item.title} ${item.target.kind === "window" ? "penceresini" : "sekmesini"} öne getir`}
        onClick={() => void focus(item.target)}>
        {item.icon ? <img src={item.icon} alt="" /> : <span aria-hidden="true">{item.title.slice(0, 1).toLocaleUpperCase("tr")}</span>}
        <span className="desktop-dock__kind" aria-hidden="true">{item.target.kind === "tab" ? "↗" : "▣"}</span>
      </button>)}
      {items.length === 0 && !error && <span className="desktop-dock__empty">Açık hedef yok</span>}
    </nav>
    </div>
    {error && <p className="desktop-dock__error" role="status">{error}</p>}
    {activity && activity.key !== dismissed && <section className="desktop-dock__preview" role="region" aria-label="Ajanın çalıştığı pencere">
      <header><span>{activity.label}</span><button type="button" aria-label="Ajan önizlemesini kapat" onClick={() => {
        dismissedRef.current = activity.key; setDismissed(activity.key); setFrame(null);
      }}>×</button></header>
      {previewError ? <p role="alert">Görüntü güncel değil: {previewError}</p>
        : frame?.key === activity.key ? <img src={frame.source} alt={`Ajan hedefi: ${activity.label}`} />
          : <p>Pencere görüntüsü bekleniyor…</p>}
    </section>}
  </aside>;
}
