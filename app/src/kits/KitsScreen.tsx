import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useState } from "react";
import { kitsFrameUrl } from "./kitsUrl";
import "./KitsScreen.css";

type KitsState =
  | { durum: "hazirlaniyor" }
  | { durum: "hazir"; adres: string }
  | { durum: "hata"; mesaj: string };

type StartKits = () => Promise<{ url: string }>;

const startWithTauri: StartKits = () => invoke<{ url: string }>("kits_baslat");

interface KitsScreenProps {
  /** Testler gerçek süreç açmadan başlatmayı taklit eder. */
  start?: StartKits;
}

/** Fusion Kits modülü: yan süreç hazır olunca iframe ile gömülür.
 *
 * Bileşen bir kez kurulur ve menü geçişinde DOM'da kalır (bkz. `MainSurface`);
 * Kits sohbeti bölüm değiştirince kaybolmaz. */
export function KitsScreen({ start = startWithTauri }: KitsScreenProps) {
  const [state, setState] = useState<KitsState>({ durum: "hazirlaniyor" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((current) => current + 1), []);

  useEffect(() => {
    let active = true;
    setState({ durum: "hazirlaniyor" });
    start()
      .then((status) => {
        if (active) setState({ durum: "hazir", adres: kitsFrameUrl(status.url) });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const mesaj = typeof error === "string" ? error : error instanceof Error ? error.message : "Kits başlatılamadı.";
        setState({ durum: "hata", mesaj });
      });
    return () => {
      active = false;
    };
  }, [attempt, start]);

  if (state.durum === "hazir") {
    return (
      <iframe
        allow="microphone; autoplay; fullscreen"
        className="kits-screen__frame"
        referrerPolicy="no-referrer"
        src={state.adres}
        title="Fusion Kits"
      />
    );
  }
  return (
    <div className="kits-screen__status" role="status">
      <h2>Kits</h2>
      {state.durum === "hazirlaniyor" ? (
        <p>Kits hazırlanıyor…</p>
      ) : (
        <>
          <p role="alert">{state.mesaj}</p>
          <button onClick={retry} type="button">Yeniden dene</button>
        </>
      )}
    </div>
  );
}
