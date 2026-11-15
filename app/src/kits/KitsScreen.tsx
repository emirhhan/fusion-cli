import { AssetHost } from "./assetHost";
import { ScheduledDeliveryClient, type ScheduleApprovalListener } from "./scheduledDeliveryClient";
import { LocalComputerHost, type ConfirmComputer, type HostRequest } from "./localComputerHost";
import { KitsBrowserHost, type ConfirmBrowser } from "./kitsBrowserHost";
import { KitsProfileHost, type ConfirmProfile } from "./kitsProfileHost";
import { FolderPickHost, type PickFolder } from "./folderPickHost";
import { KitsVoiceHost, type ConfirmMicrophone } from "./kitsVoiceHost";
import { runtimeDefault } from "../voice/useDictation";
import { askComputerAccess, askKitsBrowserAccess, askKitsProfileAccess, askMicrophoneAccess, selectProjectFolder } from "../platform/dialog";
import { useCallback, useEffect, useRef, useState } from "react";
import { startKitsWithTauri, type StartKits } from "./startKits";
import { KITS_THEME_MESSAGE, kitsFrameUrl, type KitsTheme } from "./kitsUrl";
import "./KitsScreen.css";

type KitsState =
  | { durum: "hazirlaniyor" }
  | { durum: "hazir"; adres: string }
  | { durum: "hata"; mesaj: string };

function currentTheme(): KitsTheme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

interface KitsScreenProps {
  /** Testler gerçek süreç açmadan başlatmayı taklit eder. */
  start?: StartKits;
  onDeliveryClient?: (client: ScheduledDeliveryClient | null) => void;
  /** Kits'teki zamanlanmış görev onay isteyen araçta askıda kaldı; kullanıcıya haber verilir (U5-57). */
  onScheduleApproval?: ScheduleApprovalListener;
  /** Etkin Fusion oturumuna istek; yoksa Kits'in bilgisayar isteği "bağlı değil" döner. */
  requestHost?: HostRequest;
  /** Testler yerel izin penceresini taklit eder. */
  confirmComputer?: ConfirmComputer;
  /** Kit'in kullanıcının Chrome'unu kullanma isteği için izin penceresi (P-063). */
  confirmBrowser?: ConfirmBrowser;
  /** Kit tarayıcısına Fusion profili isteği (P-023); her istekte sorulur. */
  confirmProfile?: ConfirmProfile;
  pickFolder?: PickFolder;
  /** Testler mikrofon izin penceresini taklit eder. */
  confirmMicrophone?: ConfirmMicrophone;
  /** Kits sunucusunun hâlâ aynı adreste yaşadığını yoklama aralığı (ms). */
  watchIntervalMs?: number;
  /** Bölüm gizliyken adres yoklaması durur (sürekli IPC olmasın); iframe ve köprüler yerinde kalır. */
  visible?: boolean;
  /** Başlatma bu süreden uzun sürerse durum metni gösterilir (ms). */
  statusDelayMs?: number;
  /** Başlatma bu süreyi aşarsa ilk açılışın uzun sürebileceği söylenir (ms). */
  slowHintMs?: number;
}

/** Kits süreci ölüp yeniden başlarsa YENİ bir portta açılır; iframe eski
 * adreste kalırsa her istek "Failed to fetch" verir. Bu aralıkla yoklanır. */
const KITS_WATCH_INTERVAL_MS = 5_000;
/** Ön başlatılmış Kits birkaç ms'de döner; bu sürede durum metni yanıp sönmesin. */
const KITS_STATUS_DELAY_MS = 300;
/** Ölçüldü (31 Ekim): ön başlatma yetişmezse model geçidiyle birlikte 1,1-5,3 sn. */
const KITS_SLOW_HINT_MS = 4_000;

/** Fusion Kits modülü: yan süreç hazır olunca iframe ile gömülür.
 *
 * Bileşen bir kez kurulur ve menü geçişinde DOM'da kalır (bkz. `MainSurface`);
 * Kits sohbeti bölüm değiştirince kaybolmaz. */
export function KitsScreen({
  start = startKitsWithTauri,
  onDeliveryClient,
  onScheduleApproval,
  requestHost,
  confirmComputer = askComputerAccess,
  confirmBrowser = askKitsBrowserAccess,
  confirmProfile = askKitsProfileAccess,
  pickFolder = selectProjectFolder,
  confirmMicrophone = askMicrophoneAccess,
  watchIntervalMs = KITS_WATCH_INTERVAL_MS,
  visible = true,
  statusDelayMs = KITS_STATUS_DELAY_MS,
  slowHintMs = KITS_SLOW_HINT_MS,
}: KitsScreenProps) {
  const [state, setState] = useState<KitsState>({ durum: "hazirlaniyor" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((current) => current + 1), []);
  const frame = useRef<HTMLIFrameElement>(null);
  const delivery = useRef<ScheduledDeliveryClient | null>(null);
  const voice = useRef<KitsVoiceHost | null>(null);
  // Üst bileşen satır içi işlev verse bile teslimat istemcisi her render'da yeniden kurulmaz
  // (bekleyen teslimat `finish(null)` ile düşerdi).
  const deliveryCallback = useRef(onDeliveryClient);
  deliveryCallback.current = onDeliveryClient;
  const approvalCallback = useRef(onScheduleApproval);
  approvalCallback.current = onScheduleApproval;
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    const client = new ScheduledDeliveryClient(window, frame.current.contentWindow, state.adres, (request) => approvalCallback.current?.(request));
    delivery.current = client;
    deliveryCallback.current?.(client);
    return () => { client.close(); delivery.current = null; deliveryCallback.current?.(null); };
  }, [state]);
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
    // Kit → kullanıcının Chrome'u: onay burada, komut etkin oturumun `chrome.kit_komut` RPC'sinde.
    const browser = new KitsBrowserHost(
      window,
      frame.current.contentWindow,
      state.adres,
      (name, data) => {
        const istek = hostRequest.current;
        if (!istek) return Promise.reject(new Error("Fusion oturumu yok."));
        return istek(name, data);
      },
      confirmBrowser,
    );
    return () => browser.close();
  }, [state, confirmBrowser]);
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    // Kit tarayıcısına Fusion profili (P-023): onay her istekte burada, oturum yalnız iframe'e.
    const profiles = new KitsProfileHost(
      window,
      frame.current.contentWindow,
      state.adres,
      (name, data) => {
        const istek = hostRequest.current;
        if (!istek) return Promise.reject(new Error("Fusion oturumu yok."));
        return istek(name, data);
      },
      confirmProfile,
    );
    return () => profiles.close();
  }, [state, confirmProfile]);
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    const host = new KitsVoiceHost(window, frame.current.contentWindow, state.adres, (name, data) => {
      const istek = hostRequest.current;
      if (!istek) return Promise.reject(new Error("Fusion oturumu yok; sesli yanıt için bir sohbet sekmesi aç."));
      return istek(name, data);
    }, runtimeDefault, confirmMicrophone);
    voice.current = host;
    return () => { host.close(); voice.current = null; };
  }, [state, confirmMicrophone]);
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    const folders = new FolderPickHost(window, frame.current.contentWindow, state.adres, pickFolder);
    return () => folders.close();
  }, [state, pickFolder]);
  useEffect(() => {
    if (state.durum !== "hazir" || !frame.current?.contentWindow) return;
    // Ses/bilgisayar köprüleri gibi en güncel istek fonksiyonunu ref'ten okur: sekme değişince
    // (`requestHost` kimliği değişir) süren asset istekleri yanıtsız bırakılmaz.
    const assets = new AssetHost(window, frame.current.contentWindow, state.adres, (name, data) => {
      const istek = hostRequest.current;
      if (!istek) return Promise.reject(new Error("Fusion oturumu yok."));
      return istek(name, data);
    });
    return () => assets.close();
  }, [state]);
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
        if (active) setState({ durum: "hazir", adres: kitsFrameUrl(status.url, initialTheme.current, true) });
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

  // `kits_baslat` çalışan süreci yeniden kullanır (ucuzdur); süreç ölmüşse yenisini
  // başlatıp yeni adresi döndürür. Adres değişince iframe yeni adrese taşınır.
  const address = state.durum === "hazir" ? new URL(state.adres).origin : null;
  useEffect(() => {
    if (!address || !visible) return;
    let active = true;
    let checking = false;
    const timer = window.setInterval(() => {
      if (checking) return;
      checking = true;
      start()
        .then((status) => {
          if (!active || new URL(status.url).origin === address) return;
          setState({ durum: "hazir", adres: kitsFrameUrl(status.url, currentTheme(), true) });
        })
        .catch(() => {
          // Geçici yeniden başlatma: sonraki yoklamada tekrar denenir; Kits
          // sayfası kendi "ulaşılamadı" mesajını gösterir.
        })
        .finally(() => { checking = false; });
    }, watchIntervalMs);
    return () => { active = false; window.clearInterval(timer); };
  }, [address, start, watchIntervalMs, visible]);

  if (state.durum === "hazir") {
    return (
      <iframe
        onLoad={() => { delivery.current?.reset(); voice.current?.reset(); }}
        allow="microphone; autoplay; fullscreen"
        className="kits-screen__frame"
        ref={frame}
        referrerPolicy="no-referrer"
        src={state.adres}
        title="Fusion Kits"
      />
    );
  }
  if (state.durum === "hazirlaniyor") {
    return <KitsStarting delayMs={statusDelayMs} slowHintMs={slowHintMs} />;
  }
  return (
    <div className="kits-screen__status" role="status">
      <h2>Kits</h2>
      <p role="alert">{state.mesaj}</p>
      <button onClick={retry} type="button">Yeniden dene</button>
    </div>
  );
}

interface KitsStartingProps {
  delayMs: number;
  slowHintMs: number;
}

/** Başlatma sürerken: kısa beklemede boş kalır, uzarsa ne olduğunu ve neden sürdüğünü söyler. */
function KitsStarting({ delayMs, slowHintMs }: KitsStartingProps) {
  const [phase, setPhase] = useState<"sessiz" | "basliyor" | "yavas">(delayMs > 0 ? "sessiz" : "basliyor");
  useEffect(() => {
    const timers = [
      window.setTimeout(() => setPhase((current) => (current === "sessiz" ? "basliyor" : current)), delayMs),
      window.setTimeout(() => setPhase("yavas"), Math.max(slowHintMs, delayMs)),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [delayMs, slowHintMs]);
  return (
    <div aria-busy="true" className="kits-screen__status" role="status">
      {phase !== "sessiz" && (
        <>
          <h2>Kits</h2>
          <p>Kits başlatılıyor…</p>
          {phase === "yavas" && <p className="kits-screen__hint">İlk açılışta model bağlantısı da kuruluyor; birkaç saniye sürebilir.</p>}
        </>
      )}
    </div>
  );
}
