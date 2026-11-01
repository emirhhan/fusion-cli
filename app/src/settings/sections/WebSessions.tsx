import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { Button } from "../../ui/Button";
import { WebSessionImport } from "./WebSessionImport";

/**
 * Ayarlar › Web oturumları (P-024): ajan tarayıcısına (`browser_*`) taşınan kullanıcı
 * oturumu profilleri.
 *
 * Claude in Chrome kullanıcının gerçek Chrome profilinde çalıştığı için oturumları
 * hazır bulur; Fusion'ın Playwright tarayıcısı ise boş açılır. Bu ekran o boşluğu
 * kapatır: kullanıcı oturumunu dosyadan ya da Chrome'dan bir profile aktarır, hangi
 * sitelerde geçerli olacağını onaylar, isterse varsayılan yapar. Çerez DEĞERİ bu
 * ekrana hiç gelmez — yalnız alan adı, sayı ve zaman.
 *
 * `browser.headless` / `browser.profiles_enabled` anahtarları ve "yeni profil için giriş
 * penceresi" de burada: CLI (`fusion browser set`, `fusion browser login`) ile aynı yüzey.
 */

export interface WebSessionProfile {
  ad: string;
  alan_adlari: string[];
  onayli_alan_adlari: string[];
  cerez_sayisi: number;
  kaynak: string;
  ice_aktarma: number;
  son_kullanim: number | null;
}

interface ProfilesResponse {
  ok: boolean;
  profiller?: WebSessionProfile[];
  varsayilan?: string;
  headless?: boolean;
  panel_ajan?: boolean;
  araclar?: boolean;
  etkin?: boolean;
  anahtar_var?: boolean;
  metin?: string;
}

type LoginTarget = { name: string; isNew: boolean };

const SOURCE_LABEL: Record<string, string> = { dosya: "Dosyadan", chrome: "Chrome'dan", giris: "Giriş penceresi", web_oturumu: "Model oturumundan" };
const MAX_DOMAINS_SHOWN = 4;
const LOGIN_POLL_MS = 2000;
const URL_PATTERN = /^https?:\/\//;
const PROFILE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;

/** Satırda gösterilecek alan adı özeti: ilk birkaçı + "+N". */
export function domainSummary(domains: string[]): string {
  if (domains.length <= MAX_DOMAINS_SHOWN) return domains.join(", ");
  return `${domains.slice(0, MAX_DOMAINS_SHOWN).join(", ")} +${domains.length - MAX_DOMAINS_SHOWN}`;
}

function formatTime(seconds: number | null): string {
  if (!seconds) return "hiç";
  return new Date(seconds * 1000).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

export function WebSessions({ client }: { client: ProtocolClient }) {
  const [profiles, setProfiles] = useState<WebSessionProfile[]>([]);
  const [defaultName, setDefaultName] = useState("");
  const [keyAvailable, setKeyAvailable] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [headless, setHeadless] = useState(true);
  const [panelAgent, setPanelAgent] = useState(true);
  const [browserTools, setBrowserTools] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState("");
  const [loginTarget, setLoginTarget] = useState<LoginTarget | null>(null);
  const [loginUrl, setLoginUrl] = useState("");
  const [loginOpen, setLoginOpen] = useState(false);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await client.request("tarayici.profiller", {}) as unknown as ProfilesResponse;
      if (!result.ok) throw new Error(result.metin || "Profiller okunamadı.");
      setProfiles(result.profiller ?? []);
      setDefaultName(result.varsayilan ?? "");
      setKeyAvailable(result.anahtar_var !== false);
      setEnabled(result.etkin !== false);
      setHeadless(result.headless !== false);
      setPanelAgent(result.panel_ajan !== false);
      setBrowserTools(result.araclar !== false);
      setError(result.anahtar_var === false ? result.metin ?? "" : "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Profiller okunamadı.");
    }
  }, [client]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { if (pollRef.current !== null) window.clearInterval(pollRef.current); }, []);

  const run = async (name: string, data: Record<string, unknown>, fallback: string) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await client.request(name, data) as unknown as { ok: boolean; metin?: string };
      if (!result.ok) throw new Error(result.metin || fallback);
      if (result.metin) setNotice(result.metin);
      await load();
      return result;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : fallback);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const remove = async (name: string) => {
    if (confirmDelete !== name) { setConfirmDelete(name); return; }
    setConfirmDelete("");
    await run("tarayici.sil", { ad: name }, "Profil silinemedi.");
  };

  const makeDefault = async (name: string) => {
    await run("tarayici.varsayilan", { ad: name }, "Varsayılan profil ayarlanamadı.");
  };

  const setSetting = async (key: "headless" | "profiles_enabled" | "panel_agent" | "tools", value: boolean) => {
    await run("tarayici.ayar", { anahtar: key, deger: value }, "Tarayıcı ayarı yazılamadı.");
  };

  const openLoginFor = (target: LoginTarget) => {
    setLoginTarget(target);
    setLoginUrl("");
  };

  const startLogin = async () => {
    if (!loginTarget) return;
    const name = loginTarget.name.trim();
    const result = await run("tarayici.giris", { ad: name, url: loginUrl.trim() }, "Giriş penceresi açılamadı.");
    if (!result) return;
    const pid = (result as { pid?: number }).pid;
    setLoginOpen(true);
    setNotice("Giriş penceresi açıldı. Siteye girip pencereyi kapatınca oturum profile yazılır.");
    pollRef.current = window.setInterval(() => {
      void client.request("tarayici.giris_durumu", { pid }).then(async (value) => {
        const state = value as unknown as { ok: boolean; acik?: boolean; metin?: string };
        if (state.acik) return;
        if (pollRef.current !== null) window.clearInterval(pollRef.current);
        pollRef.current = null;
        setLoginOpen(false);
        setLoginTarget(null);
        setLoginUrl("");
        // Önce liste tazelenir (`load` hata satırını sıfırlar), sonra sonuç yazılır:
        // alt sürecin sebebi ("playwright install chromium") kaybolmasın.
        await load();
        if (state.ok) {
          setNotice("Giriş penceresi kapandı; oturum kaydedildi.");
        } else {
          setNotice("");
          setError(state.metin ?? "Giriş penceresi hata ile kapandı.");
        }
      }).catch(() => { /* yoklama hatası geçicidir; sonraki tik yeniden dener */ });
    }, LOGIN_POLL_MS);
  };

  const loginNameValid = loginTarget !== null && PROFILE_NAME_PATTERN.test(loginTarget.name.trim());
  const canOpenLogin = !busy && !loginOpen && loginNameValid && URL_PATTERN.test(loginUrl.trim());

  return (
    <>
      <article className="settings__card">
        <h3>Web oturumları</h3>
        <p className="settings__hint">
          Fusion'ın kendi tarayıcısı (browser_* araçları) normalde girişsiz açılır. Buradaki profiller
          senin oturumunu ona taşır: çerezler şifreli saklanır, yalnız onayladığın sitelerde kullanılır ve
          bu ekranda hiçbir çerez değeri gösterilmez. Ajan bir profili yüklemeden önce her seferinde onay ister.
        </p>
        <label className="settings__row settings__row--check">
          <input
            checked={enabled}
            disabled={busy}
            id="websession-enabled"
            onChange={(event) => void setSetting("profiles_enabled", event.target.checked)}
            type="checkbox"
          />
          <span>Ajan tarayıcı profillerini yükleyebilsin (browser.profiles_enabled)</span>
        </label>
        <label className="settings__row settings__row--check">
          <input
            checked={!headless}
            disabled={busy}
            id="websession-headed"
            onChange={(event) => void setSetting("headless", !event.target.checked)}
            type="checkbox"
          />
          <span>Tarayıcı penceresi görünür açılsın (browser.headless: false)</span>
        </label>
        <label className="settings__row settings__row--check">
          <input
            checked={panelAgent}
            disabled={busy}
            id="websession-panel-agent"
            onChange={(event) => void setSetting("panel_agent", event.target.checked)}
            type="checkbox"
          />
          <span>Ajan uygulama içi Tarayıcı panelini kullansın; tarayıcı turlar arasında açık kalır (browser.panel_agent)</span>
        </label>
        <label className="settings__row settings__row--check">
          <input
            checked={browserTools}
            disabled={busy}
            id="websession-browser-tools"
            onChange={(event) => void setSetting("tools", event.target.checked)}
            type="checkbox"
          />
          <span>Browser tools: ajan yerleşik tarayıcı araçlarını kullanabilsin; kapalıyken panel yalnız senin içindir (browser.tools)</span>
        </label>
        {!enabled && <p className="settings__inline-error" role="status">Profiller kapalı: ajan hiçbir oturumu yüklemez; açık istek bile reddedilir.</p>}
        {profiles.length === 0 ? (
          <p className="settings__hint">Henüz profil yok. Aşağıdan bir çerez dosyası ya da Chrome profili aktar, ya da yeni profil için giriş penceresi aç.</p>
        ) : (
          <ul className="settings__list" aria-label="Tarayıcı profilleri">
            {profiles.map((profile) => (
              <li key={profile.ad}>
                <div className="settings__row">
                  <div>
                    <strong>{profile.ad}</strong>
                    {defaultName === profile.ad && <span className="settings__badge"> varsayılan</span>}
                    <div className="settings__hint">
                      {domainSummary(profile.alan_adlari)} · {profile.cerez_sayisi} çerez · {SOURCE_LABEL[profile.kaynak] ?? profile.kaynak}
                      {" · son kullanım: "}{formatTime(profile.son_kullanim)}
                    </div>
                    {profile.onayli_alan_adlari.length > 0 && (
                      <div className="settings__hint">Onaylı siteler: {profile.onayli_alan_adlari.join(", ")}</div>
                    )}
                  </div>
                  <div className="settings__actions">
                    {defaultName !== profile.ad && (
                      <Button disabled={busy} onClick={() => void makeDefault(profile.ad)} variant="secondary">Varsayılan yap</Button>
                    )}
                    <Button disabled={busy || loginOpen} onClick={() => openLoginFor({ name: profile.ad, isNew: false })} variant="secondary">Giriş penceresi aç</Button>
                    <Button disabled={busy} onClick={() => void remove(profile.ad)} variant="danger">
                      {confirmDelete === profile.ad ? "Evet, sil" : "Sil"}
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="settings__actions">
          <Button disabled={busy || loginOpen || !keyAvailable} onClick={() => openLoginFor({ name: "", isNew: true })} variant="secondary">Yeni profil için giriş…</Button>
          {defaultName && (
            <Button disabled={busy} onClick={() => void makeDefault("")} variant="ghost">Varsayılanı kaldır</Button>
          )}
          <small>{defaultName ? "Varsayılan kaldırılınca tarayıcı yine çerezsiz açılır." : "Görünür pencerede siteye girersin; pencere kapanınca oturum profile yazılır."}</small>
        </div>
        {loginTarget && (
          <div className="settings__form">
            {loginTarget.isNew && (
              <>
                <label htmlFor="websession-login-name">Yeni profil adı</label>
                <input
                  id="websession-login-name"
                  disabled={loginOpen}
                  onChange={(event) => setLoginTarget({ name: event.target.value, isNew: true })}
                  placeholder="ör. is-hesabi"
                  value={loginTarget.name}
                />
              </>
            )}
            <label htmlFor="websession-login-url">{loginTarget.isNew ? "Giriş adresi" : `${loginTarget.name} için giriş adresi`}</label>
            <input id="websession-login-url" disabled={loginOpen} onChange={(event) => setLoginUrl(event.target.value)} placeholder="https://…" value={loginUrl} />
            <div className="settings__actions">
              <Button disabled={!canOpenLogin} onClick={() => void startLogin()} variant="primary">Pencereyi aç</Button>
              <Button disabled={loginOpen} onClick={() => setLoginTarget(null)} variant="ghost">Vazgeç</Button>
            </div>
          </div>
        )}
        {notice && <p className="settings__hint" role="status">{notice}</p>}
        {error && <p className="settings__inline-error" role="alert">{error}</p>}
      </article>
      <WebSessionImport client={client} disabled={!keyAvailable || busy} onImported={(message) => { setNotice(message); void load(); }} />
    </>
  );
}
