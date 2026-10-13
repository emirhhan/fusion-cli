import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, operationResult, type CommandResult } from "../protocol/result";
import { searchSettings } from "./search";
import type { ProtocolClient } from "../protocol/client";
import type { ThemePreference } from "../theme/theme";
import { Button } from "../ui/Button";
import { Icon, type IconName } from "../ui/Icon";
import { UpdatePanel } from "../control/UpdatePanel";
import { Instructions } from "./Instructions";
import { MemoryPanel } from "./MemoryPanel";
import { UsagePanel } from "./UsagePanel";
import { VoicePreferences } from "./VoicePreferences";
import { General, readHistoryOpen, HISTORY_KEY } from "./sections/General";
import { Models, type ModelState } from "./sections/Models";
import { Permissions } from "./sections/Permissions";
import { Advanced } from "./sections/Advanced";
import { ChromeBrowser } from "./ChromeBrowser";
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

type BolumId = "genel" | "hesap" | "ses" | "kisisellestirme" | "modeller" | "tarayici" | "izinler" | "guncellemeler" | "gelismis";

const BOLUMLER: { id: BolumId; etiket: string; ikon: IconName; grup: string }[] = [
  { id: "genel", etiket: "Genel", ikon: "settings", grup: "Kişisel" },
  { id: "hesap", etiket: "Hesap", ikon: "user", grup: "Kişisel" },
  { id: "ses", etiket: "Ses", ikon: "mic", grup: "Kişisel" },
  { id: "kisisellestirme", etiket: "Kişiselleştirme", ikon: "lessons", grup: "Kişisel" },
  { id: "modeller", etiket: "Modeller", ikon: "skills", grup: "Entegrasyonlar" },
  { id: "tarayici", etiket: "Tarayıcı", ikon: "preview", grup: "Entegrasyonlar" },
  { id: "izinler", etiket: "İzinler", ikon: "help", grup: "Entegrasyonlar" },
  { id: "guncellemeler", etiket: "Güncellemeler", ikon: "changes", grup: "Sistem" },
  { id: "gelismis", etiket: "Gelişmiş", ikon: "terminal", grup: "Sistem" },
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
  initialSection?: BolumId;
  onClose: () => void;
  onThemeChange: (preference: ThemePreference) => void;
  themePreference: ThemePreference;
  /** Hesabım ekranını açar. Verilmezse hesap bölümü yalnız bilgi gösterir. */
  onOpenAccount?: () => void;
  onChangeRoot?: () => void;
  onRunCommand?: (command: string) => void | CommandResult | Promise<void | CommandResult>;
}

export function Settings({
  client,
  initialSection = "genel",
  onChangeRoot,
  onClose,
  onOpenAccount,
  onRunCommand,
  onThemeChange,
  themePreference,
}: SettingsProps) {
  const [bolum, setBolum] = useState<BolumId>(initialSection);
  const [control, setControl] = useState<ControlSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(readHistoryOpen);
  const [gatewayBusy, setGatewayBusy] = useState(false);
  const [modeBusy, setModeBusy] = useState(false);
  const [gatewayError, setGatewayError] = useState<{ message: string; retry: () => void } | null>(null);
  const [modeError, setModeError] = useState<{ message: string; retry: () => void } | null>(null);
  const [controlLoading, setControlLoading] = useState(true);
  const owner = useRef(0);
  const loadSequence = useRef(0);
  const gatewayGuard = useRef(false);
  const modeGuard = useRef(false);
  const [focusRow, setFocusRow] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => setBolum(initialSection), [initialSection]);

  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement
      ? document.activeElement : null;
    dialogRef.current?.focus();
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
    const generation = owner.current, sequence = ++loadSequence.current;
    setControlLoading(true);
    try {
      const durum = (await client.request("kontrol.durum", {})) as ControlSnapshot & {
        ok?: boolean;
        metin?: string;
      };
      // Eskiden `ok` hiç kontrol edilmiyordu: çekirdek `{ok:false, metin:"…"}`
      // döndürdüğünde bile (istek REDDEDİLMEZ, yalnız BAŞARISIZ sonuçla
      // ÇÖZÜLÜR — bkz. `ProtocolClient`) ekran onu geçerli bir durum gibi
      // gösteriyordu; kullanıcı hiçbir hata görmüyordu ama sayfa bozuk
      // kalıyordu. `catch` bloğu da GERÇEK nedeni atıyor, sabit bir metinle
      // örtüyordu — bu dosyanın altındaki `bellek`/`kontrol.anahtar_*`
      // çağrıları gibi asıl sebep gösterilmeliydi.
      if (generation !== owner.current || sequence !== loadSequence.current) return;
      if (durum?.ok === false) throw new Error(durum.metin || "Ayarlar okunamadı.");
      setControl(durum ?? null);
      setError(null); setControlLoading(false);
    } catch (reason) {
      if (generation !== owner.current || sequence !== loadSequence.current) return;
      setControlLoading(false);
      setError(`Ayarlar okunamadı: ${String(reason instanceof Error ? reason.message : reason)}`);
    }
  }, [client]);

  useEffect(() => {
    const generation = ++owner.current;
    gatewayGuard.current = false; modeGuard.current = false;
    setControl(null); setError(null);
    setGatewayBusy(false); setModeBusy(false); setGatewayError(null); setModeError(null);
    void load();
    return () => { owner.current = generation + 1; };
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
    if (!control || gatewayGuard.current) return;
    gatewayGuard.current = true; setGatewayBusy(true); setGatewayError(null);
    const generation = owner.current;
    const endpoint = gatewayRunning ? "kontrol.gateway_durdur" : "kontrol.gateway_baslat";
    const run = async () => {
      try {
        const payload = await client.request(endpoint, {});
        if (generation !== owner.current) return;
        const result = operationResult(payload, "Yerel API ucu değiştirilemedi.");
        if (!result.ok) { setGatewayError({ message: result.message, retry: toggleGateway }); return; }
        await load();
      } catch (reason) { if (generation === owner.current) setGatewayError({ message: errorMessage(reason), retry: toggleGateway }); }
      finally { if (generation === owner.current) { gatewayGuard.current = false; setGatewayBusy(false); } }
    };
    void run();
  };
  const selectMode = (command: string) => {
    if (!control || !onRunCommand || modeGuard.current) return;
    modeGuard.current = true; setModeBusy(true); setModeError(null);
    const generation = owner.current;
    const run = async () => {
      try {
        const response = onRunCommand(command);
        const payload = await response;
        if (generation !== owner.current) return;
        const result = operationResult(payload, "Çalışma modu değiştirilemedi.", true);
        if (!result.ok) { setModeError({ message: result.message, retry: () => selectMode(command) }); return; }
        await load();
      } catch (reason) { if (generation === owner.current) setModeError({ message: errorMessage(reason), retry: () => selectMode(command) }); }
      finally { if (generation === owner.current) { modeGuard.current = false; setModeBusy(false); } }
    };
    void run();
  };
  const searchResults = searchSettings(search);
  useEffect(() => {
    if (!focusRow) return;
    const target = document.getElementById(focusRow);
    if (!target) return;
    if (!target.matches("input,select,button,textarea")) target.tabIndex = -1;
    target.focus(); setFocusRow(null);
  }, [bolum, focusRow]);

  return (
    <section className="settings" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div aria-labelledby="settings-title" aria-modal="true" className="settings__dialog" ref={dialogRef} role="dialog" tabIndex={-1}>
        <div className="settings__navcol">
          <h2 className="settings__sr-only" id="settings-title">Ayarlar</h2>
          <button aria-label="Ayarları kapat" className="settings__close" onClick={onClose} type="button"><span aria-hidden="true">←</span> Uygulamaya geri dön</button>
          <input aria-label="Ayarları ara" className="settings__search" onChange={(event) => setSearch(event.target.value)} placeholder="Ayarları ara" type="search" value={search} />
          {search.trim() && <div><p role="status">{searchResults.length ? `${searchResults.length} sonuç` : BOLUMLER.some((item) => item.etiket.toLocaleLowerCase("tr").includes(search.trim().toLocaleLowerCase("tr"))) ? "Bölüm eşleşmeleri" : "Sonuç bulunamadı"}</p>
            {searchResults.map((row) => <button key={row.id} onClick={() => { setBolum(row.section); setFocusRow(row.id); }}>{row.label}</button>)}</div>}
          <nav aria-label="Ayar bölümleri" className="settings__nav">
            {["Kişisel", "Entegrasyonlar", "Sistem"].map((grup) => {
              const items = BOLUMLER.filter((item) => item.grup === grup && item.etiket.toLocaleLowerCase("tr").includes(search.trim().toLocaleLowerCase("tr")));
              if (!items.length) return null;
              return <div className="settings__nav-group" key={grup}>
                <span className="settings__nav-label">{grup}</span>
                {items.map((item) => <button
                  aria-current={bolum === item.id ? "page" : undefined}
                  key={item.id}
                  onClick={() => setBolum(item.id)}
                  type="button"
                >
                  <Icon name={item.ikon} size={16} />
                  <span>{item.etiket}</span>
                </button>)}
              </div>;
            })}
          </nav>
        </div>

        <div className="settings__panel">
          <h3 className="settings__section-heading">{BOLUMLER.find((item) => item.id === bolum)?.etiket}</h3>
          {controlLoading && <p role="status">Ayarlar yükleniyor…</p>}
          {gatewayError && <p role="alert">{gatewayError.message} <button onClick={gatewayError.retry} disabled={gatewayBusy}>Yeniden dene</button></p>}
          {modeError && <p role="alert">{modeError.message} <button onClick={modeError.retry} disabled={modeBusy}>Yeniden dene</button></p>}
          {error && (
            <p className="settings__error" role="status">
              {error}{" "}
              <button className="settings__error-retry" onClick={() => void load()} type="button">
                Yeniden dene
              </button>
            </p>
          )}
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

          {bolum === "ses" && <VoicePreferences client={client} />}

          {bolum === "kisisellestirme" && <><MemoryPanel client={client} /><Instructions client={client} /></>}

          {bolum === "tarayici" && <ChromeBrowser client={client} />}

          {bolum === "izinler" && (
            <Permissions
              kok={control?.kok ?? ""}
              kokleSinirli={control?.izin?.kokle_sinirli !== false}
              mod={control?.izin?.mod ?? "auto"}
              pending={modeBusy || !control}
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
                mesgul={gatewayBusy || !control}
                onToggle={toggleGateway}
              />
              <UsagePanel client={client} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
