import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ThemePreference } from "../theme/theme";
import { Button } from "../ui/Button";
import { UpdatePanel } from "../control/UpdatePanel";
import { Instructions } from "./Instructions";
import { MemoryPanel } from "./MemoryPanel";
import { UsagePanel } from "./UsagePanel";
import { VoicePreferences } from "./VoicePreferences";
import { General, readHistoryOpen, HISTORY_KEY } from "./sections/General";
import { Models, type ModelState } from "./sections/Models";
import { Permissions } from "./sections/Permissions";
import { Advanced } from "./sections/Advanced";
import "./Settings.css";

/**
 * Ayarlar — macOS tarzı sol menü, tek kolon içerik.
 *
 * Eskiden her şey tek sayfada kart kart akıyordu: tema tercihiyle gateway
 * durumu, gizlilik metniyle MCP sayısı aynı yığındaydı ve aranan şey
 * bulunamıyordu. Bölümler artık ayrı; her biri TEK bir soruyu cevaplar.
 *
 * Kontrol Paneli ile ayrım korunur: orası SAĞLAYICI bağlantılarını yönetir
 * (anahtarlar, web oturumları), burası kullanıcının tercihleri ve sistemin
 * ayarlanabilir yanı.
 */

type BolumId = "genel" | "hesap" | "kisisellestirme" | "modeller" | "izinler" | "guncellemeler" | "gelismis";

const BOLUMLER: { id: BolumId; etiket: string }[] = [
  { id: "genel", etiket: "Genel" },
  { id: "hesap", etiket: "Hesap" },
  { id: "kisisellestirme", etiket: "Kişiselleştirme" },
  { id: "modeller", etiket: "Modeller" },
  { id: "izinler", etiket: "İzinler" },
  { id: "guncellemeler", etiket: "Güncellemeler" },
  { id: "gelismis", etiket: "Gelişmiş" },
];

interface ControlSnapshot {
  gateway?: { adres?: string; durum?: string };
  izin?: { mod?: string; kokle_sinirli?: boolean };
  kok?: string;
  model?: ModelState;
  saglayicilar?: { id: string; kurulu?: boolean }[];
}

interface SettingsProps {
  client: ProtocolClient;
  onClose: () => void;
  onThemeChange: (preference: ThemePreference) => void;
  themePreference: ThemePreference;
  /** Hesabım ekranını açar. Verilmezse hesap bölümü yalnız bilgi gösterir. */
  onOpenAccount?: () => void;
  onChangeRoot?: () => void;
  onRunCommand?: (command: string) => void | Promise<void>;
}

export function Settings({
  client,
  onChangeRoot,
  onClose,
  onOpenAccount,
  onRunCommand,
  onThemeChange,
  themePreference,
}: SettingsProps) {
  const [bolum, setBolum] = useState<BolumId>("genel");
  const [control, setControl] = useState<ControlSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(readHistoryOpen);
  const [gatewayBusy, setGatewayBusy] = useState(false);
  const [search, setSearch] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement
      ? document.activeElement : null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const controls = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]',
      )).filter((item) => item.getClientRects().length > 0);
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previousFocus.current?.focus();
    };
  }, [onClose]);

  const load = useCallback(async () => {
    try {
      const durum = (await client.request("kontrol.durum", {})) as ControlSnapshot & {
        ok?: boolean;
      };
      setControl(durum ?? null);
      setError(null);
    } catch {
      setError("Ayarlar okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  const changeHistory = (open: boolean) => {
    setHistoryOpen(open);
    try {
      localStorage.setItem(HISTORY_KEY, String(open));
    } catch {
      // Yazılamıyorsa tercih bu oturumda geçerli olur; ekran yine çalışır.
    }
  };

  const gatewayRunning = control?.gateway?.durum === "calisiyor";
  const toggleGateway = () => {
    setGatewayBusy(true);
    const uc = gatewayRunning ? "kontrol.gateway_durdur" : "kontrol.gateway_baslat";
    void client
      .request(uc, {})
      .then(() => load())
      .catch(() => setError("Yerel API ucu değiştirilemedi."))
      .finally(() => setGatewayBusy(false));
  };

  const selectMode = (command: string) => {
    if (!onRunCommand) return;
    void Promise.resolve(onRunCommand(command))
      .then(load)
      .catch(() => setError("Çalışma modu değiştirilemedi."));
  };

  return (
    <section className="settings" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div aria-labelledby="settings-title" aria-modal="true" className="settings__dialog" ref={dialogRef} role="dialog">
        <div className="settings__navcol">
          <h2 className="settings__sr-only" id="settings-title">Ayarlar</h2>
          <button aria-label="Ayarları kapat" className="settings__close" onClick={onClose} ref={closeRef} type="button">×</button>
          <input aria-label="Ayarları ara" className="settings__search" onChange={(event) => setSearch(event.target.value)} placeholder="Ayarları ara" type="search" value={search} />
          <nav aria-label="Ayar bölümleri" className="settings__nav">
            {BOLUMLER.filter((item) => item.etiket.toLocaleLowerCase("tr").includes(search.trim().toLocaleLowerCase("tr"))).map((item) => (
            <button
              aria-current={bolum === item.id ? "page" : undefined}
              key={item.id}
              onClick={() => setBolum(item.id)}
              type="button"
            >
              {item.etiket}
            </button>
            ))}
          </nav>
        </div>

        <div className="settings__panel">
          <h3 className="settings__section-heading">{BOLUMLER.find((item) => item.id === bolum)?.etiket}</h3>
          {error && <p className="settings__error" role="status">{error}</p>}
          {bolum === "genel" && (
            <General
              historyOpen={historyOpen}
              onHistoryChange={changeHistory}
              onThemeChange={onThemeChange}
              themePreference={themePreference}
            />
          )}

          {bolum === "hesap" && (
            <article className="settings__card">
              <h3>Hesap</h3>
              <p className="settings__hint">
                Hesabın, parolan ve avatarın bu bilgisayarda tutulur. Hiçbir bilgi
                sunucuya gönderilmez; hesabı silersen ya da Fusion'ı kaldırırsan
                verileri de gider.
              </p>
              {onOpenAccount && (
                <div className="settings__actions">
                  <Button onClick={onOpenAccount} variant="secondary">
                    Hesabımı aç
                  </Button>
                </div>
              )}
            </article>
          )}

          {bolum === "modeller" && (
            <Models model={control?.model ?? null} onRunCommand={onRunCommand} />
          )}

          {bolum === "kisisellestirme" && <><MemoryPanel client={client} /><Instructions client={client} /></>}

          {bolum === "izinler" && (
            <Permissions
              kok={control?.kok ?? ""}
              kokleSinirli={control?.izin?.kokle_sinirli !== false}
              mod={control?.izin?.mod ?? "auto"}
              onChangeRoot={onChangeRoot}
              onSelectMode={onRunCommand ? selectMode : undefined}
            />
          )}

          {bolum === "guncellemeler" && <UpdatePanel />}

          {bolum === "gelismis" && (
            <>
              <Advanced
                adres={control?.gateway?.adres ?? ""}
                calisiyor={gatewayRunning}
                mesgul={gatewayBusy}
                onToggle={toggleGateway}
              />
              <UsagePanel client={client} />
              <VoicePreferences client={client} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
