import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { PreviewLog } from "../workspace/PreviewLog";
import { BrowserToolbar } from "./BrowserToolbar";
import { LiveScreen } from "./LiveScreen";
import { useBrowserLive } from "./useBrowserLive";
import {
  BROWSER_RPC,
  BROWSER_VIEWPORTS,
  addressFromInput,
  decodeBox,
  decodePick,
  decodeState,
  errorText,
  type BrowserState,
} from "./browserPanelProtocol";
import "./BrowserPanel.css";

/**
 * Uygulama içi Tarayıcı paneli (P-045).
 *
 * Ajanın `browser_*` araçlarıyla AYNI tarayıcıyı gösterir: kullanıcı ajanın tıkladığını canlı
 * izler, sekmeler arasında gezer, kendisi tıklar/yazar. Tur sürerken yapılan girdi denetimi
 * devralır ("Ajana bırak" ile geri verilir). Öğe seçici (P-041) seçilen öğenin seçicisini ve
 * görüntüsünü sohbete ekler.
 */
export interface BrowserPick { metin: string; yol: string }
export interface BrowserRequest { url: string; pick: boolean; seq: number }

export interface BrowserPanelProps {
  client: ProtocolClient;
  /** Önizleme panelinden "Tarayıcıda aç / Öğe seç" isteği; `seq` aynı adresin tekrarını ayırır. */
  request?: BrowserRequest | null;
  /** Seçilen öğe ya da görüntü sohbete eklenir (metin taslağa, görsel eke). */
  onPick?: (pick: BrowserPick) => void;
}

type Drawer = "none" | "console";

export function BrowserPanel({ client, request = null, onPick }: BrowserPanelProps) {
  const live = useBrowserLive(client);
  const [status, setStatus] = useState<BrowserState | null>(null);
  const [profiles, setProfiles] = useState<string[]>([]);
  const [panelProfile, setPanelProfile] = useState("");
  const [address, setAddress] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const [drawer, setDrawer] = useState<Drawer>("none");
  const [viewportId, setViewportId] = useState<string>(BROWSER_VIEWPORTS[0].id);
  const snapshot = live.snapshot;
  const state = snapshot ?? status;
  const isOpen = Boolean(snapshot?.acik);

  const call = async (name: string, data: Record<string, unknown> = {}) => {
    setError(null);
    try {
      const payload = await client.request(`${BROWSER_RPC}${name}`, data);
      if (payload.ok !== true) {
        setError(errorText(payload, "Tarayıcı isteği yapılamadı."));
        return null;
      }
      if ("acik" in payload) setStatus(decodeState(payload));
      live.refresh();
      return payload;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tarayıcı isteği yapılamadı.");
      return null;
    }
  };

  useEffect(() => {
    let alive = true;
    void client.request(`${BROWSER_RPC}durum`, {}).then((payload) => {
      if (!alive || payload.ok !== true) return;
      setStatus(decodeState(payload));
      setProfiles(Array.isArray(payload.profiller) ? payload.profiller.filter((p): p is string => typeof p === "string") : []);
      setPanelProfile(typeof payload.panel_profili === "string" ? payload.panel_profili : "");
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [client]);

  useEffect(() => {
    if (!editing && snapshot?.url) setAddress(snapshot.url);
  }, [snapshot?.url, editing]);

  const go = async (raw: string) => {
    const url = addressFromInput(raw);
    if (!url) return;
    setBusy(true);
    setEditing(false);
    await call(isOpen ? "git" : "ac", { url });
    setBusy(false);
  };

  useEffect(() => {
    if (!request) return;
    setAddress(request.url);
    setPicking(request.pick);
    void go(request.url);
    // Yalnız yeni istek tetikler; `go` her çizimde yeniden kurulur.
  }, [request?.seq]);

  const pick = async (x: number, y: number) => {
    const payload = await call("oge_sec", { x, y });
    if (!payload) return;
    try {
      const picked = decodePick(payload);
      setPicking(false);
      onPick?.({ metin: picked.metin, yol: picked.yol });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Öğe seçilemedi.");
    }
  };

  const hover = async (x: number, y: number) => {
    const payload = await client.request(`${BROWSER_RPC}oge`, { x, y });
    return payload.ok === true ? decodeBox(payload.kutu) : null;
  };

  const attachScreenshot = async () => {
    const payload = await call("ekran");
    if (payload && typeof payload.yol === "string") {
      onPick?.({ metin: typeof payload.metin === "string" ? payload.metin : "", yol: payload.yol });
    }
  };

  const resize = (id: string) => {
    setViewportId(id);
    const viewport = BROWSER_VIEWPORTS.find((item) => item.id === id) ?? BROWSER_VIEWPORTS[0];
    void call("boyut", { genislik: viewport.width, yukseklik: viewport.height });
  };

  const userHasControl = state?.denetim === "kullanici";
  const agentWorking = Boolean(state?.turSuruyor && state.ajanGoruyor);

  return (
    <div className="browser-panel">
      <BrowserToolbar
        address={address}
        busy={busy}
        isOpen={isOpen}
        onAddressChange={(value) => { setEditing(true); setAddress(value); }}
        onConsole={() => setDrawer((current) => (current === "console" ? "none" : "console"))}
        onHistory={(step) => void call(step)}
        onPickToggle={() => setPicking((current) => !current)}
        onScreenshot={() => void attachScreenshot()}
        onSubmit={() => void go(address)}
        onViewport={resize}
        consoleOpen={drawer === "console"}
        picking={picking}
        viewportId={viewportId}
      />

      {isOpen && snapshot && (
        <div aria-label="Tarayıcı sekmeleri" className="browser-tabs" role="tablist">
          {snapshot.sekmeler.map((tab) => (
            <div className="browser-tabs__tab" data-active={tab.etkin} key={`${tab.no}-${tab.url}`}>
              <button
                aria-selected={tab.etkin}
                onClick={() => void call("sekme_sec", { no: tab.no })}
                role="tab"
                title={tab.url}
                type="button"
              >
                {tab.baslik || tab.url || "Yeni sekme"}
              </button>
              {snapshot.sekmeler.length > 1 && (
                <button aria-label={`${tab.baslik || tab.url} sekmesini kapat`} className="browser-tabs__close" onClick={() => void call("sekme_kapat", { no: tab.no })} type="button">×</button>
              )}
            </div>
          ))}
          <button aria-label="Yeni sekme" className="browser-tabs__new" onClick={() => void call("sekme_ac")} title="Yeni sekme" type="button">+</button>
        </div>
      )}

      {userHasControl ? (
        <div className="browser-banner browser-banner--user" data-waiting={state?.ajanBekliyor || undefined} role="status">
          {state?.ajanBekliyor ? (
            <span><strong>Ajan seni bekliyor.</strong> İşin bitince denetimi ajana bırak.</span>
          ) : (
            <span><strong>Denetim sende.</strong> Ajanın tarayıcı eylemleri sen bırakana kadar bekler.</span>
          )}
          <button onClick={() => void call("birak")} type="button">Ajana bırak</button>
        </div>
      ) : agentWorking ? (
        <div className="browser-banner browser-banner--agent" role="status">
          <span className="browser-banner__pulse" aria-hidden="true" />
          <span>Ajan bu tarayıcıyı kullanıyor; tıklar ya da yazarsan denetim sana geçer.</span>
          <button onClick={() => void call("devral")} type="button">Devral</button>
        </div>
      ) : null}

      {(error ?? live.error) && <p className="browser-panel__error" role="alert">{error ?? live.error}</p>}

      <div className="browser-panel__stage">
        {isOpen && live.frame ? (
          <LiveScreen
            frame={live.frame}
            onClick={(x, y, clicks) => void call("tikla", { x, y, tik: clicks })}
            onHover={hover}
            onKey={(key) => void call("tus", { tus: key })}
            onPick={(x, y) => void pick(x, y)}
            onScroll={(x, y, dx, dy) => void call("kaydir", { x, y, dx, dy })}
            onType={(metin) => void call("yaz", { metin })}
            picking={picking}
            title={snapshot?.baslik ?? ""}
          />
        ) : (
          <div className="browser-panel__empty">
            <strong>{isOpen ? "Sayfa yükleniyor…" : "Uygulama içi tarayıcı"}</strong>
            <p>
              {isOpen
                ? "Görüntü birazdan gelir."
                : "Bir adres yaz ya da ajandan bir siteyi açmasını iste; ajanın tarayıcıda yaptığı her şey burada canlı görünür."}
            </p>
          </div>
        )}
        {drawer === "console" && isOpen && (
          <PreviewLog clearable client={client} onClose={() => setDrawer("none")} rpc={`${BROWSER_RPC}konsol`} url={snapshot?.url ?? ""} />
        )}
      </div>

      <BrowserSessionMenu
        onClose={() => void call("kapat")}
        onConsent={(value) => void call("ayar", { anahtar: "profil_onayi", deger: value })}
        onProfile={(name) => void call("profil", { ad: name })}
        onShare={(value) => void call("ayar", { anahtar: "ajan_paylasir", deger: value })}
        panelProfile={panelProfile}
        profiles={profiles}
        state={state}
      />
    </div>
  );
}

interface BrowserSessionMenuProps {
  state: BrowserState | null;
  profiles: string[];
  panelProfile: string;
  onProfile: (name: string) => void;
  onShare: (value: boolean) => void;
  onConsent: (value: boolean) => void;
  onClose: () => void;
}

/** Oturum ayarları: profil (temiz / kalıcı panel oturumu / kayıtlı), ajan paylaşımı, kapatma. */
function BrowserSessionMenu({ state, profiles, panelProfile, onProfile, onShare, onConsent, onClose }: BrowserSessionMenuProps) {
  const current = state?.kullaniciProfili ?? "";
  const others = profiles.filter((name) => name !== panelProfile);
  return (
    <footer className="browser-session">
      <label>
        <span>Oturum</span>
        <select aria-label="Tarayıcı oturumu" onChange={(event) => onProfile(event.target.value)} value={current}>
          <option value="">Temiz (çıkınca silinir)</option>
          {panelProfile && <option value={panelProfile}>Panel oturumu (çerezleri sakla)</option>}
          {others.map((name) => <option key={name} value={name}>Profil: {name}</option>)}
        </select>
      </label>
      <label className="browser-session__check">
        <input checked={state?.ajanPaylasir ?? true} onChange={(event) => onShare(event.target.checked)} type="checkbox" />
        Ajan bu tarayıcıyı kullanır
      </label>
      {current && (
        <label className="browser-session__check browser-session__check--warn">
          <input checked={state?.profilOnayi ?? false} onChange={(event) => onConsent(event.target.checked)} type="checkbox" />
          Ajan girişli oturumu kullanabilir
        </label>
      )}
      {state?.acik && <button onClick={onClose} type="button">Tarayıcıyı kapat</button>}
    </footer>
  );
}
