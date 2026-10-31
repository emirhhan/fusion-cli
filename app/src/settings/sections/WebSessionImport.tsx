import { useEffect, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import type { ProtocolClient } from "../../protocol/client";
import { Button } from "../../ui/Button";

/**
 * Web oturumu içe aktarma formu (P-024): dosyadan (cookies.txt / JSON), Chrome'dan ya da
 * bir web MODEL oturumundan (ChatGPT/Claude/Gemini/Copilot aboneliği; P-023).
 *
 * Akış iki adımdır ve ikincisi alan adı ONAYIDIR: önce yalnız alan adları okunur
 * (Chrome'da Keychain'e dokunmadan), kullanıcı hangi sitelerin aktarılacağını
 * işaretler, sonra çerezler şifreli profile yazılır. Çerez değeri bu ekrana hiç gelmez.
 *
 * Hiçbir alan adı önceden işaretli gelmez. Ölçüldü (31 Ekim): hepsi işaretli gelince
 * "Alan adlarını göster → İçe aktar" iki tıkla bankalar ve e-posta dahil bütün Chrome
 * oturumunu ajana taşıyordu; onay listesi fiilen "hepsi" oluyordu.
 *
 * Model oturumundan aktarma TEK YÖNLÜ bir kopyadır: abonelik oturumu değişmez ve hiçbir
 * zaman kendiliğinden paylaşılmaz; yalnız işaretlenen sitelerin çerezi profile girer.
 */

type Source = "dosya" | "chrome" | "model";

interface ChromeProfileRow { dizin: string; ad: string }
interface WebSessionRow { saglayici: string; hesap: string }

interface ImportResult { ok: boolean; metin?: string }

const MODEL_NOTE =
  "Abonelik oturumunun işaretlediğin sitelerdeki çerezleri ajanın tarayıcısına kopyalanır. Tek yönlüdür; model oturumu değişmez. Profili yükleyen her ajan çağrısı ayrıca onay ister.";
const sessionKey = (row: WebSessionRow) => `${row.saglayici}/${row.hesap}`;

const CHROME_NOTE =
  "Chrome'dan aktarırken macOS bir Keychain izni sorar; 'İzin ver' demeden hiçbir çerez okunmaz.";

export function WebSessionImport({
  client,
  disabled,
  onImported,
}: {
  client: ProtocolClient;
  disabled?: boolean;
  onImported: (message: string) => void;
}) {
  const [source, setSource] = useState<Source>("dosya");
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [chromeProfiles, setChromeProfiles] = useState<ChromeProfileRow[]>([]);
  const [chromeProfile, setChromeProfile] = useState("");
  const [webSessions, setWebSessions] = useState<WebSessionRow[]>([]);
  const [webSession, setWebSession] = useState("");
  const [domains, setDomains] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (source !== "chrome") return;
    let mounted = true;
    void client.request("tarayici.chrome_profilleri", {}).then((value) => {
      if (!mounted) return;
      const result = value as unknown as { ok: boolean; profiller?: ChromeProfileRow[]; metin?: string };
      if (!result.ok) { setError(result.metin ?? "Chrome profilleri okunamadı."); return; }
      const rows = result.profiller ?? [];
      setChromeProfiles(rows);
      setChromeProfile((current) => current || rows[0]?.dizin || "");
    }).catch(() => { if (mounted) setError("Chrome profilleri okunamadı."); });
    return () => { mounted = false; };
  }, [client, source]);

  useEffect(() => {
    if (source !== "model") return;
    let mounted = true;
    void client.request("tarayici.web_oturumlari", {}).then((value) => {
      if (!mounted) return;
      const result = value as unknown as { ok: boolean; oturumlar?: WebSessionRow[]; metin?: string };
      if (!result.ok) { setError(result.metin ?? "Web oturumları okunamadı."); return; }
      const rows = result.oturumlar ?? [];
      setWebSessions(rows);
      setWebSession((current) => current || (rows[0] ? sessionKey(rows[0]) : ""));
    }).catch(() => { if (mounted) setError("Web oturumları okunamadı."); });
    return () => { mounted = false; };
  }, [client, source]);

  const resetPreview = () => { setDomains([]); setSelected(new Set()); };
  const chosenSession = () => webSessions.find((row) => sessionKey(row) === webSession);

  const pickFile = async () => {
    const { selectFiles } = await import("../../platform/dialog");
    const [chosen] = await selectFiles();
    if (chosen) { setPath(chosen); resetPreview(); }
  };

  const preview = async () => {
    setBusy(true);
    setError("");
    try {
      const row = chosenSession();
      const value = source === "dosya"
        ? await client.request("tarayici.dosya_onizle", { yol: path })
        : source === "model"
          ? await client.request("tarayici.web_oturumlari", { saglayici: row?.saglayici ?? "", hesap: row?.hesap ?? "main" })
          : await client.request("tarayici.chrome_profilleri", { chrome_profil: chromeProfile });
      const result = value as unknown as { ok: boolean; alan_adlari?: string[]; metin?: string };
      if (!result.ok) throw new Error(result.metin || "Önizleme alınamadı.");
      setDomains(result.alan_adlari ?? []);
      setSelected(new Set());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Önizleme alınamadı.");
    } finally {
      setBusy(false);
    }
  };

  const toggle = (domain: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(domain)) next.delete(domain); else next.add(domain);
      return next;
    });
  };

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const data: Record<string, unknown> = { ad: name.trim(), alan_adlari: [...selected] };
      let method = "tarayici.ice_aktar";
      if (source === "dosya") data.yol = path;
      else if (source === "chrome") data.chrome_profil = chromeProfile;
      else {
        const row = chosenSession();
        method = "tarayici.web_oturumu_aktar";
        data.saglayici = row?.saglayici ?? "";
        data.hesap = row?.hesap ?? "main";
      }
      const result = await client.request(method, data) as unknown as ImportResult;
      if (!result.ok) throw new Error(result.metin || "İçe aktarma başarısız.");
      onImported(result.metin ?? "Profil yazıldı.");
      setName("");
      setPath("");
      resetPreview();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "İçe aktarma başarısız.");
    } finally {
      setBusy(false);
    }
  };

  const sourceReady = source === "dosya" ? path.trim() !== "" : source === "chrome" ? chromeProfile !== "" : webSession !== "";
  const canPreview = !disabled && !busy && sourceReady;
  const canSubmit = canPreview && name.trim() !== "" && selected.size > 0;

  return (
    <article className="settings__card">
      <h3>Oturum içe aktar</h3>
      <div className="settings__choices" role="group" aria-label="Kaynak">
        <button aria-pressed={source === "dosya"} className="settings__choice" data-active={source === "dosya"} onClick={() => { setSource("dosya"); resetPreview(); }} type="button">
          <strong>Dosyadan</strong>
          <span>Tarayıcı eklentisiyle dışa aktarılan cookies.txt ya da JSON</span>
        </button>
        <button aria-pressed={source === "chrome"} className="settings__choice" data-active={source === "chrome"} onClick={() => { setSource("chrome"); resetPreview(); }} type="button">
          <strong>Chrome'dan</strong>
          <span>Bu bilgisayardaki Chrome profilinin oturumları</span>
        </button>
        <button aria-pressed={source === "model"} className="settings__choice" data-active={source === "model"} onClick={() => { setSource("model"); resetPreview(); }} type="button">
          <strong>Model oturumundan aktar</strong>
          <span>ChatGPT/Claude/Gemini/Copilot web oturumunun seçtiğin siteleri (tek yönlü kopya)</span>
        </button>
      </div>
      <div className="settings__form">
        <label htmlFor="websession-name">Profil adı</label>
        <input id="websession-name" disabled={disabled} onChange={(event) => setName(event.target.value)} placeholder="ör. is-hesabi" value={name} />
        {source === "dosya" ? (
          <>
            <label htmlFor="websession-path">Çerez dosyası</label>
            <input id="websession-path" disabled={disabled} onChange={(event) => { setPath(event.target.value); resetPreview(); }} placeholder="/Users/…/cookies.txt" value={path} />
            {isTauri() && <button disabled={disabled || busy} onClick={() => void pickFile()} type="button">Dosya seç…</button>}
          </>
        ) : source === "model" ? (
          <>
            <label htmlFor="websession-model">Web model oturumu</label>
            <select id="websession-model" disabled={disabled || webSessions.length === 0} onChange={(event) => { setWebSession(event.target.value); resetPreview(); }} value={webSession}>
              {webSessions.map((row) => <option key={sessionKey(row)} value={sessionKey(row)}>{row.saglayici} ({row.hesap})</option>)}
            </select>
            {webSessions.length === 0 && <p className="settings__hint">Bu bilgisayarda web model oturumu yok; önce Modeller bölümünden giriş yap.</p>}
            <p className="settings__hint" role="note">{MODEL_NOTE}</p>
          </>
        ) : (
          <>
            <label htmlFor="websession-chrome">Chrome profili</label>
            <select id="websession-chrome" disabled={disabled || chromeProfiles.length === 0} onChange={(event) => { setChromeProfile(event.target.value); resetPreview(); }} value={chromeProfile}>
              {chromeProfiles.map((row) => <option key={row.dizin} value={row.dizin}>{row.ad} ({row.dizin})</option>)}
            </select>
            <p className="settings__hint">{CHROME_NOTE}</p>
          </>
        )}
      </div>
      <div className="settings__actions">
        <Button disabled={!canPreview} onClick={() => void preview()} variant="secondary">Alan adlarını göster</Button>
        <small>Önce hangi sitelerin aktarılacağını görür ve işaretlersin; hiçbiri hazır seçili gelmez.</small>
      </div>
      {domains.length > 0 && (
        <>
          <div className="settings__actions">
            <Button disabled={busy} onClick={() => setSelected(new Set(domains))} variant="ghost">Hepsini seç</Button>
            <Button disabled={busy || selected.size === 0} onClick={() => setSelected(new Set())} variant="ghost">Temizle</Button>
          </div>
          <ul className="settings__list" aria-label="Aktarılacak alan adları">
            {domains.map((domain) => (
              <li key={domain}>
                <label>
                  <input checked={selected.has(domain)} onChange={() => toggle(domain)} type="checkbox" /> {domain}
                </label>
              </li>
            ))}
          </ul>
          <div className="settings__actions">
            <Button disabled={!canSubmit} onClick={() => void submit()} variant="primary">İçe aktar</Button>
            <small>
              {selected.size === 0
                ? "Aktarılacak siteyi işaretle; seçimsiz içe aktarma yok."
                : `${selected.size} alan adı seçili. Profil yalnız bu sitelerde çerez taşır.`}
            </small>
          </div>
        </>
      )}
      {error && <p className="settings__inline-error" role="alert">{error}</p>}
    </article>
  );
}
