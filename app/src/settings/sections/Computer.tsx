import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { Button } from "../../ui/Button";
import { ChoiceCards, Field, PanelGroup, PanelIntro, ToggleRow } from "../PanelParts";
import "./Computer.css";

/**
 * Ayarlar › Bu bilgisayar — bilgisayar kullanımı (computer use) tercihleri (P-006, P-007).
 *
 * Claude Desktop "This computer" karşılığı: etkinleştirme anahtarı, kademe tavanı (yalnız bak /
 * tıkla / tam kontrol), kategori tablosu, reddedilen uygulamalar, uygulama başına kademe ve
 * tur davranışı (arka plan, gizlenenleri geri göster, Esc ile durdur). Değerler çekirdekte
 * `desktop:` bölümüne yazılır (`bilgisayar.ayar_yaz`); CLI'de `fusion config set desktop.<alan>`.
 */

export type ComputerLevel = "observe" | "click" | "full";

export interface ComputerSettings {
  enabled: boolean;
  control_level: ComputerLevel;
  category_defaults: boolean;
  denied_apps: string[];
  app_levels: string[];
  app_consent: boolean;
  background: boolean;
  unhide_on_finish: boolean;
  escape_stops: boolean;
}

type Key = keyof ComputerSettings;

const LEVELS: { value: ComputerLevel; title: string; description: string }[] = [
  { value: "observe", title: "Yalnız bak", description: "Ekranı görür; tıklamaz, yazmaz." },
  { value: "click", title: "Tıkla", description: "Tıklar ve kaydırır; yazmaz, kısayol kullanmaz." },
  { value: "full", title: "Tam kontrol", description: "Tıklar, yazar, sürükler, kısayol kullanır." },
];

const LEVEL_LABEL: Record<ComputerLevel, string> = { observe: "Yalnız bak", click: "Tıkla", full: "Tam kontrol" };

function readSettings(value: unknown): ComputerSettings | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const list = (item: unknown) => (Array.isArray(item) ? item.filter((entry): entry is string => typeof entry === "string") : []);
  const level = raw.control_level === "observe" || raw.control_level === "click" ? raw.control_level : "full";
  return {
    enabled: raw.enabled !== false,
    control_level: level,
    category_defaults: raw.category_defaults !== false,
    denied_apps: list(raw.denied_apps),
    app_levels: list(raw.app_levels),
    app_consent: raw.app_consent !== false,
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
  const [newLevelApp, setNewLevelApp] = useState("");
  const [newLevel, setNewLevel] = useState<ComputerLevel>("click");
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
  const addLevel = () => {
    const name = newLevelApp.trim();
    if (!name || name.includes("=") || name.includes(",")) return;
    const kept = settings.app_levels.filter((entry) => entry.split("=")[0].trim().toLocaleLowerCase("tr") !== name.toLocaleLowerCase("tr"));
    setNewLevelApp("");
    void save("app_levels", [...kept, `${name}=${newLevel}`]);
  };
  const off = !settings.enabled;

  return (
    <article className="settings__card" data-testid="computer-settings" id="settings-computer">
      <PanelIntro title="Bilgisayar kullanımı">
        Fusion'ın ekranı görmesi, tıklaması ve yazması. Her eylem yine onay politikasından geçer;
        gönder, sil, öde gibi riskli düğmeler ve Sistem Ayarları her seferinde sorulur.
      </PanelIntro>
      {error && <p className="settings__warning" role="alert">{error}</p>}
      {notice && <p className="settings__hint" role="status">{notice}</p>}

      <PanelGroup title="Erişim">
        <ToggleRow
          checked={settings.enabled}
          description="Kapalıyken desktop_* araçları modele hiç sunulmaz."
          disabled={busy === "enabled"}
          onChange={(value) => void save("enabled", value)}
          title="Bilgisayar kullanımını etkinleştir"
        />
        <ChoiceCards
          disabled={off || busy === "control_level"}
          legend="Uygulamalar en çok"
          name="computer-level"
          note="Tavandır: kategori ya da uygulama ayarı bunu aşamaz."
          onChange={(value) => void save("control_level", value as ComputerLevel)}
          options={LEVELS}
          value={settings.control_level}
        />
        <ToggleRow
          checked={settings.category_defaults}
          description="Tarayıcılar yalnız bak, terminal ve IDE'ler tıkla; yatırım, kripto ve parola yöneticileri engelli."
          disabled={off || busy === "category_defaults"}
          onChange={(value) => void save("category_defaults", value)}
          title="Kategori kademeleri"
        />
        <ToggleRow
          checked={settings.app_consent}
          description="Bir uygulama oturumda ilk kez kullanılırken sorulur: Bu oturum / Reddet / Her zaman reddet."
          disabled={off || busy === "app_consent"}
          onChange={(value) => void save("app_consent", value)}
          title="Uygulama başına onay"
        />
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
        <Field label="Uygulama ekle" hint="Ad ya da paket kimliği (com.apple.Mail).">
          {(id) => (
            <div className="computer-settings__add">
              <input id={id} list="computer-running-apps" onChange={(event) => setNewDenied(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") addDenied(); }} value={newDenied} />
              <datalist id="computer-running-apps">{apps.map((name) => <option key={name} value={name} />)}</datalist>
              <Button disabled={busy !== null || !newDenied.trim()} onClick={addDenied} variant="primary">Reddet</Button>
            </div>
          )}
        </Field>
      </PanelGroup>

      <PanelGroup note="Kategori kademesini ezer; tavanı ve ret listesini ezmez." title="Uygulama kademeleri">
        {settings.app_levels.length === 0 && <p className="px-note">Uygulamaya özel kademe yok; kategori kademesi geçerli.</p>}
        {settings.app_levels.length > 0 && <ul aria-label="Uygulama kademeleri" className="computer-settings__list">
          {settings.app_levels.map((entry) => {
            const [name, level] = entry.split("=");
            return (
              <li key={entry}>
                <span>{name.trim()} · {LEVEL_LABEL[(level?.trim() as ComputerLevel)] ?? level}</span>
                <Button disabled={busy !== null} onClick={() => void save("app_levels", settings.app_levels.filter((item) => item !== entry))} variant="secondary">Kaldır</Button>
              </li>
            );
          })}
        </ul>}
        <Field label="Kademe ekle">
          {(id) => (
            <div className="computer-settings__add">
              <input aria-label="Uygulama adı" id={id} list="computer-running-apps" onChange={(event) => setNewLevelApp(event.target.value)} value={newLevelApp} />
              <select aria-label="Kademe" onChange={(event) => setNewLevel(event.target.value as ComputerLevel)} value={newLevel}>
                {LEVELS.map((level) => <option key={level.value} value={level.value}>{level.title}</option>)}
              </select>
              <Button disabled={busy !== null || !newLevelApp.trim()} onClick={addLevel} variant="primary">Ekle</Button>
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
          title="Bitince uygulamaları geri göster"
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
