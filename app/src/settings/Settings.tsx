import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ThemePreference } from "../theme/theme";
import "./Settings.css";

/**
 * Ayarlar — Kontrol Paneli'nden AYRI ekran.
 *
 * Ayrım bilinçlidir: Kontrol Paneli çalışan sistemi YÖNETİR (model düzeni,
 * anahtarlar, gateway, MCP). Ayarlar ise kullanıcının kendi TERCİHLERİNİ ve
 * durum özetini taşır — görünüm, arayüz davranışı, bağlantı özeti, gizlilik.
 * İkisini tek ekrana yığmak, sık kullanılan tercihleri yönetim ayrıntısının
 * altına gömüyordu.
 */

/** Kenar çubuğundaki geçmiş bölümünün açık başlayıp başlamayacağı. */
const HISTORY_KEY = "fusion.sidebar.history-open.v1";

interface ControlSnapshot {
  gateway?: { adres?: string; durum?: string };
  kok?: string;
  mcp?: { ad: string }[];
  saglayicilar?: { id: string; kurulu?: boolean }[];
}

interface SettingsProps {
  client: ProtocolClient;
  onClose: () => void;
  onThemeChange: (preference: ThemePreference) => void;
  themePreference: ThemePreference;
}

function readHistoryOpen(): boolean {
  try {
    return localStorage.getItem(HISTORY_KEY) !== "false";
  } catch {
    // Özel pencerede depo erişilemez olabilir; varsayılan açıktır.
    return true;
  }
}

export function Settings({ client, onClose, onThemeChange, themePreference }: SettingsProps) {
  const [control, setControl] = useState<ControlSnapshot | null>(null);
  const [webConnected, setWebConnected] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(readHistoryOpen);

  const load = useCallback(async () => {
    try {
      const [durum, web] = await Promise.all([
        client.request("kontrol.durum", {}) as Promise<ControlSnapshot & { ok?: boolean }>,
        client.request("web.saglayicilar", {}) as Promise<{
          ok?: boolean;
          saglayicilar?: { bagli?: boolean }[];
        }>,
      ]);
      setControl(durum ?? null);
      setWebConnected((web?.saglayicilar ?? []).filter((item) => item.bagli).length);
      setError(null);
    } catch {
      setError("Ayarlar okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleHistory = () => {
    const next = !historyOpen;
    setHistoryOpen(next);
    try {
      localStorage.setItem(HISTORY_KEY, String(next));
    } catch {
      // Yazılamıyorsa tercih bu oturumda geçerli olur; ekran yine çalışır.
    }
  };

  const keyProviders = (control?.saglayicilar ?? []).filter((item) => item.kurulu).length;
  const connections = keyProviders + webConnected;
  const gatewayRunning = control?.gateway?.durum === "calisiyor";

  return (
    <section aria-label="Ayarlar" className="settings">
      <header className="settings__head">
        <div>
          <span>TERCİHLER</span>
          <h2>Ayarlar</h2>
          <p>Görünüm, arayüz davranışı ve bu bilgisayardaki durumun özeti.</p>
        </div>
        <button className="settings__close" onClick={onClose} type="button">
          Kapat
        </button>
      </header>

      {error && <p className="settings__error" role="status">{error}</p>}

      <div className="settings__grid">
        <article className="settings__card">
          <h3>Görünüm</h3>
          <label className="settings__row" htmlFor="settings-theme">
            <span>Görünüm</span>
            <select
              id="settings-theme"
              onChange={(event) => onThemeChange(event.target.value as ThemePreference)}
              value={themePreference}
            >
              <option value="system">Sistemi izle</option>
              <option value="light">Açık</option>
              <option value="dark">Koyu</option>
            </select>
          </label>
          <label className="settings__row settings__row--check">
            <input
              checked={historyOpen}
              id="settings-history"
              onChange={toggleHistory}
              type="checkbox"
            />
            <span>Geçmiş bölümünü açık başlat</span>
          </label>
        </article>

        <article className="settings__card">
          <h3>Çalışma alanı</h3>
          <dl className="settings__pairs">
            <dt>Etkin klasör</dt>
            <dd>{control?.kok ?? "—"}</dd>
            <dt>Araç bağlantıları</dt>
            <dd>{(control?.mcp ?? []).length} MCP sunucusu</dd>
          </dl>
        </article>

        <article className="settings__card">
          <h3>Bağlantılar</h3>
          <p className="settings__stat">{connections} bağlı bağlantı</p>
          <p className="settings__hint">
            {gatewayRunning ? "Gateway çalışıyor" : "Gateway kapalı"}
          </p>
          <p className="settings__hint">
            Sağlayıcıları eklemek ve çıkarmak Kontrol Paneli'ndedir.
          </p>
        </article>

        <article className="settings__card">
          <h3>Gizlilik</h3>
          <p className="settings__hint">
            Sohbetleriniz, projeleriniz ve anahtarlarınız dahil tüm verileriniz bu cihazda
            kalır. Fusion bunları hiçbir sunucuya kopyalamaz; yalnız sizin seçtiğiniz
            modele, sizin gönderdiğiniz mesajı iletir.
          </p>
        </article>
      </div>
    </section>
  );
}
