import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { KITS_THEME_MESSAGE, kitsFrameUrl, type KitsTheme } from "./kitsUrl";
import "./KitsScreen.css";

type KitsState =
  | { durum: "hazirlaniyor" }
  | { durum: "hazir"; adres: string }
  | { durum: "hata"; mesaj: string };

type StartKits = () => Promise<{ url: string }>;

const startWithTauri: StartKits = () => invoke<{ url: string }>("kits_baslat");

function currentTheme(): KitsTheme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

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
  const frame = useRef<HTMLIFrameElement>(null);
  // Adres ilk açılıştaki temayı taşır; sonraki değişiklik sayfayı yeniden yüklemeden
  // (sohbet kaybolmadan) mesajla iletilir.
  const initialTheme = useRef<KitsTheme>(currentTheme());

  useEffect(() => {
    if (state.durum !== "hazir") return;
    const origin = new URL(state.adres).origin;
    const send = () =>
      frame.current?.contentWindow?.postMessage({ type: KITS_THEME_MESSAGE, theme: currentTheme() }, origin);
    const observer = new MutationObserver(send);
    observer.observe(document.documentElement, { attributeFilter: ["data-theme"], attributes: true });
    return () => observer.disconnect();
  }, [state]);

  useEffect(() => {
    let active = true;
    setState({ durum: "hazirlaniyor" });
    start()
      .then((status) => {
        if (active) setState({ durum: "hazir", adres: kitsFrameUrl(status.url, initialTheme.current) });
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
        ref={frame}
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
