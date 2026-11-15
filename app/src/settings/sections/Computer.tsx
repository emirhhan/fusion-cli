import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { Button } from "../../ui/Button";
import { Field, PanelGroup, PanelIntro, ToggleRow } from "../PanelParts";
import "./Computer.css";

/**
 * Ayarlar › Bu bilgisayar — bilgisayar kullanımı (computer use) tercihleri (P-006, P-007).
 *
 * Claude Desktop "This computer" karşılığı: etkinleştirme anahtarı (varsayılan kapalı, #420),
 * sabit kademe tablosu (#424: "These tiers are fixed by app category and can't be changed"),
 * reddedilen uygulamalar ve tur davranışı (arka plan, gizlenenleri geri göster, Esc ile durdur).
 * Değerler çekirdekte `desktop:` bölümüne yazılır (`bilgisayar.ayar_yaz`).
 */

export interface ComputerSettings {
  enabled: boolean;
  denied_apps: string[];
  background: boolean;
  unhide_on_finish: boolean;
  escape_stops: boolean;
}

type Key = keyof ComputerSettings;

/** Claude Desktop "App permissions" tablosu; değiştirilemez. */
const TIERS: { title: string; can: string; applies: string }[] = [
  { title: "Yalnız bak", can: "Uygulamayı ekran görüntüsünde görür", applies: "Tarayıcılar, yatırım platformları" },
  { title: "Tıkla", can: "Tıklar ve kaydırır; yazmaz, kısayol kullanmaz", applies: "Terminaller, IDE'ler" },
  { title: "Tam kontrol", can: "Tıklar, yazar, sürükler, kısayol kullanır", applies: "Diğer her şey" },
];

function readSettings(value: unknown): ComputerSettings | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const list = (item: unknown) => (Array.isArray(item) ? item.filter((entry): entry is string => typeof entry === "string") : []);
  return {
    enabled: raw.enabled === true,
    denied_apps: list(raw.denied_apps),
    background: raw.background !== false,
    unhide_on_finish: raw.unhide_on_finish !== false,
    escape_stops: raw.escape_stops !== false,
  };
}

export function Computer({ client }: { client: Pick<ProtocolClient, "request"> }) {
  const [settings, setSettings] = useState<ComputerSettings | null>(null);
  const [apps, setApps] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<Key | null>(null);
  const [newDenied, setNewDenied] = useState("");
  const alive = useRef(true);

  const load = useCallback(async () => {
    try {
      const payload = await client.request("bilgisayar.ayarlar", {});
      if (!alive.current) return;
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Bilgisayar ayarları okunamadı."));
      setSettings(readSettings(payload.ayarlar));
      setError(null);
    } catch (reason) {
      if (alive.current) setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [client]);

  useEffect(() => {
    alive.current = true;
    void load();
    void client.request("bilgisayar.uygulamalar", {}).then((payload) => {
      if (alive.current && payload.ok === true && Array.isArray(payload.uygulamalar)) {
        setApps(payload.uygulamalar.filter((item): item is string => typeof item === "string"));
      }
    }).catch(() => undefined);
    return () => { alive.current = false; };
  }, [client, load]);

  const save = async (key: Key, value: ComputerSettings[Key]) => {
    if (busy) return;
    setBusy(key); setError(null);
    try {
      const payload = await client.request("bilgisayar.ayar_yaz", { anahtar: key, deger: value });
      if (!alive.current) return;
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Ayar kaydedilemedi."));
      setSettings(readSettings(payload.ayarlar));
      setNotice(String(payload.metin ?? ""));
    } catch (reason) {
      if (alive.current) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  if (!settings) {
    return (
      <article className="settings__card" data-testid="computer-settings">
        {error ? <p className="settings__warning" role="alert">{error} <button onClick={() => void load()} type="button">Yeniden dene</button></p>
          : <p role="status">Bilgisayar ayarları yükleniyor…</p>}
      </article>
    );
  }

  const addDenied = () => {
    const name = newDenied.trim();
    if (!name || settings.denied_apps.some((item) => item.toLocaleLowerCase("tr") === name.toLocaleLowerCase("tr"))) return;
    setNewDenied("");
    void save("denied_apps", [...settings.denied_apps, name]);
  };
  const off = !settings.enabled;

  return (
    <article className="settings__card" data-testid="computer-settings" id="settings-computer">
      <PanelIntro title="Bilgisayar kullanımı">
        Fusion'ın ekranı görmesi, tıklaması ve yazması. Bir uygulama oturumda ilk kez
        kullanılırken "Bu oturum için izin ver / Reddet" sorulur.
      </PanelIntro>
      {error && <p className="settings__warning" role="alert">{error}</p>}
      {notice && <p className="settings__hint" role="status">{notice}</p>}

      <PanelGroup title="Erişim">
        <ToggleRow
          checked={settings.enabled}
          description="Kapalıyken desktop_* araçları modele hiç sunulmaz."
          disabled={busy === "enabled"}
          onChange={(value) => void save("enabled", value)}
          title="Computer use'u etkinleştir"
        />
      </PanelGroup>

      <PanelGroup note="Kademeler uygulama kategorisine göre sabittir ve değiştirilemez." title="Uygulama izinleri">
        <table aria-label="Uygulama kademeleri" className="computer-settings__tiers">
          <thead><tr><th scope="col">Kademe</th><th scope="col">Yapabildiği</th><th scope="col">Uygulandığı</th></tr></thead>
          <tbody>{TIERS.map((tier) => <tr key={tier.title}><th scope="row">{tier.title}</th><td>{tier.can}</td><td>{tier.applies}</td></tr>)}</tbody>
        </table>
      </PanelGroup>

      <PanelGroup note="Fusion bu uygulamalara tıklamaz, yazmaz; pencereleri ekran görüntüsüne ve pencere listelerine girmez (dışlanamıyorsa görüntü alınmaz)." title="Reddedilen uygulamalar">
        {settings.denied_apps.length === 0 && <p className="px-note">Reddedilen uygulama yok.</p>}
        {settings.denied_apps.length > 0 && <ul aria-label="Reddedilen uygulamalar" className="computer-settings__list">
          {settings.denied_apps.map((name) => (
            <li key={name}>
              <span>{name}</span>
              <Button disabled={busy !== null} onClick={() => void save("denied_apps", settings.denied_apps.filter((item) => item !== name))} variant="secondary">Kaldır</Button>
            </li>
          ))}
        </ul>}
        <Field label="Uygulama ekle" hint="Ad ya da paket kimliği (com.apple.Mail); Windows'ta exe adı (notepad.exe).">
          {(id) => (
            <div className="computer-settings__add">
              <input id={id} list="computer-running-apps" onChange={(event) => setNewDenied(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") addDenied(); }} value={newDenied} />
              <datalist id="computer-running-apps">{apps.map((name) => <option key={name} value={name} />)}</datalist>
              <Button disabled={busy !== null || !newDenied.trim()} onClick={addDenied} variant="primary">Reddet</Button>
            </div>
          )}
        </Field>
      </PanelGroup>

      <PanelGroup title="Tur davranışı">
        <ToggleRow
          checked={settings.background}
          description="Açıkken diğer uygulamalar gizlenmez; sen çalışmaya devam edersin. Kapalıyken ilk ekran eyleminde hedef uygulama ve Fusion dışındakiler gizlenir."
          disabled={off || busy === "background"}
          onChange={(value) => void save("background", value)}
          title="Arka planda çalış"
        />
        <ToggleRow
          checked={settings.unhide_on_finish}
          description="Tur bitince Fusion'ın gizlediği uygulamalar yeniden gösterilir."
          disabled={off || busy === "unhide_on_finish"}
          onChange={(value) => void save("unhide_on_finish", value)}
          title="Bitince uygulamaları geri göster (Unhide apps when Claude finishes)"
        />
        <ToggleRow
          checked={settings.escape_stops}
          description="Fusion fareyi ya da klavyeyi kullanırken fiziksel Esc turu durdurur; tuş uygulamaya gitmez."
          disabled={off || busy === "escape_stops"}
          onChange={(value) => void save("escape_stops", value)}
          title="Esc ile durdur"
        />
      </PanelGroup>
    </article>
  );
}
