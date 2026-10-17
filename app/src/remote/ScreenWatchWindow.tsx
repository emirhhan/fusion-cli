import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
import { remoteInUse } from "./remoteFlag";
import "./ScreenWatchWindow.css";

/** Etkin oturum yoklama aralığı ve kare yenileme aralığı (ms): telefonun kare hızından yavaş, masaüstünü yormaz. */
export const WATCH_POLL_MS = 2000;
export const WATCH_FRAME_MS = 1000;

interface Watched {
  cihazId: string;
  ad: string;
}

/**
 * Telefon masaüstü ekranını izlerken küçük, kapatılabilir izleme penceresi.
 *
 * Ek ekran yakalaması YAPMAZ: çekirdekten telefona en son verilen kareyi ister (`uzak.ekran_onizleme`),
 * yani "telefonun gördüğü" gösterilir. Pencereyi kapatmak yalnız bu görünümü gizler; paylaşımı
 * kesmek için "Kes" kullanılır.
 */
export function ScreenWatchWindow({ client }: { client: ProtocolClient | null }) {
  const [live, setLive] = useState<Watched[]>([]);
  const [frames, setFrames] = useState<Record<string, string>>({});
  const [dismissed, setDismissed] = useState<string[]>([]);

  useEffect(() => {
    if (!client || !remoteInUse()) return;
    let stopped = false;
    const poll = async () => {
      try {
        const result = await client.request("uzak.ekran_bekleyen", {});
        if (stopped || result.ok !== true) return;
        const next = (Array.isArray(result.etkin) ? result.etkin : []) as Watched[];
        setLive(next);
        setDismissed((current) => current.filter((id) => next.some((item) => item.cihazId === id)));
      } catch {
        if (!stopped) setLive([]);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), WATCH_POLL_MS);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [client]);

  const visible = live.filter((item) => !dismissed.includes(item.cihazId));
  const key = visible.map((item) => item.cihazId).join(",");

  useEffect(() => {
    if (!client || visible.length === 0) return;
    let stopped = false;
    const pull = async () => {
      for (const item of visible) {
        try {
          const result = await client.request("uzak.ekran_onizleme", { cihazId: item.cihazId });
          if (!stopped && result.ok === true && typeof result.jpegBase64 === "string") {
            setFrames((current) => ({ ...current, [item.cihazId]: `data:image/jpeg;base64,${result.jpegBase64}` }));
          }
        } catch {
          // Kare gelmezse son kare kalır; sonraki turda yeniden denenir.
        }
      }
    };
    void pull();
    const timer = window.setInterval(() => void pull(), WATCH_FRAME_MS);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [client, key]);

  const cut = useCallback(
    async (id: string) => { await client?.request("uzak.ekran_kes", { cihazId: id }); },
    [client],
  );

  if (visible.length === 0) return null;
  return (
    <div className="screen-watch" role="region" aria-label="Ekran izleme">
      {visible.map((item) => (
        <section className="screen-watch__window" key={item.cihazId} aria-label={`${item.ad} ekranı izliyor`}>
          <header className="screen-watch__bar">
            <span className="screen-watch__title">{item.ad} ekranını izliyor</span>
            <Button onClick={() => void cut(item.cihazId)}>Kes</Button>
            <button
              className="screen-watch__close"
              type="button"
              aria-label="İzleme penceresini kapat"
              onClick={() => setDismissed((current) => [...current, item.cihazId])}
            >
              ×
            </button>
          </header>
          {frames[item.cihazId]
            ? <img className="screen-watch__frame" src={frames[item.cihazId]} alt={`${item.ad} cihazının gördüğü ekran`} />
            : <p className="screen-watch__wait">İlk kare bekleniyor…</p>}
        </section>
      ))}
    </div>
  );
}
