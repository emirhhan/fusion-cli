import { ScheduledDeliveryClient } from "./scheduledDeliveryClient";
import { LocalComputerHost, type ConfirmComputer, type HostRequest } from "./localComputerHost";
import { FolderPickHost, type PickFolder } from "./folderPickHost";
import { askComputerAccess, selectProjectFolder } from "../platform/dialog";
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
  onDeliveryClient?: (client: ScheduledDeliveryClient | null) => void;
  /** Etkin Fusion oturumuna istek; yoksa Kits'in bilgisayar isteği "bağlı değil" döner. */
  requestHost?: HostRequest;
  /** Testler yerel izin penceresini taklit eder. */
  confirmComputer?: ConfirmComputer;
  pickFolder?: PickFolder;
}

/** Fusion Kits modülü: yan süreç hazır olunca iframe ile gömülür.
 *
 * Bileşen bir kez kurulur ve menü geçişinde DOM'da kalır (bkz. `MainSurface`);
 * Kits sohbeti bölüm değiştirince kaybolmaz. */
export function KitsScreen({
  start = startWithTauri,
  onDeliveryClient,
  requestHost,
  confirmComputer = askComputerAccess,
  pickFolder = selectProjectFolder,
}: KitsScreenProps) {
  const [state, setState] = useState<KitsState>({ durum: "hazirlaniyor" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((current) => current + 1), []);
  const frame = useRef<HTMLIFrameElement>(null);
  const delivery = useRef<ScheduledDeliveryClient | null>(null);
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    const client = new ScheduledDeliveryClient(window, frame.current.contentWindow, state.adres);
    delivery.current = client;
    onDeliveryClient?.(client);
    return () => { client.close(); delivery.current = null; onDeliveryClient?.(null); };
  }, [state, onDeliveryClient]);
  // Oturum değişince (sekme) en güncel istek fonksiyonu kullanılır; dinleyici yeniden kurulmaz.
  const hostRequest = useRef<HostRequest | undefined>(requestHost);
  hostRequest.current = requestHost;
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    const computer = new LocalComputerHost(
      window,
      frame.current.contentWindow,
      state.adres,
      (name, data) => {
        const istek = hostRequest.current;
        if (!istek) return Promise.reject(new Error("Fusion oturumu yok."));
        return istek(name, data);
      },
      confirmComputer,
    );
    return () => computer.close();
  }, [state, confirmComputer]);
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    const folders = new FolderPickHost(window, frame.current.contentWindow, state.adres, pickFolder);
    return () => folders.close();
  }, [state, pickFolder]);
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
        onLoad={() => delivery.current?.reset()}
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
