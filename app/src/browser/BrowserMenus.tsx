import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { decodeRows, type LaunchConfigRow } from "../workspace/PreviewLaunch";
import { readOpenLinksInside, saveOpenLinksInside } from "./openLinks";

/** Açılır menü kabuğu: dışarı tık ve Esc kapatır. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) close(); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", escape); };
  }, [open, close]);
  return ref;
}

export interface BrowserMoreMenuProps {
  client: ProtocolClient;
  keepCookies: boolean;
  onKeepCookies: (value: boolean) => void;
  onClearData: () => void;
}

/** Browser ⋮ menüsü (#439): Keep cookies, Clear browsing data, Auto-verify changes, Open links in built-in browser. */
export function BrowserMoreMenu({ client, keepCookies, onKeepCookies, onClearData }: BrowserMoreMenuProps) {
  const [open, setOpen] = useState(false);
  const [autoVerify, setAutoVerify] = useState<boolean | null>(null);
  const [openLinks, setOpenLinks] = useState(readOpenLinksInside);
  const [error, setError] = useState("");
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);

  useEffect(() => {
    if (!open) return;
    void client.request("onizleme.yapilandirmalar", {}).then((payload) => {
      setAutoVerify(typeof payload.otomatik_dogrulama === "boolean" ? payload.otomatik_dogrulama : true);
    }).catch(() => setAutoVerify(null));
  }, [client, open]);

  const toggleAutoVerify = async (value: boolean) => {
    setError("");
    const payload = await client.request("onizleme.otomatik_dogrulama", { deger: value }).catch(() => null);
    if (payload?.ok === true) setAutoVerify(value);
    else setError(typeof payload?.metin === "string" ? payload.metin : "Auto-verify değiştirilemedi.");
  };

  return (
    <div className="browser-menu" ref={ref}>
      <button aria-expanded={open} aria-haspopup="menu" aria-label="Tarayıcı seçenekleri" onClick={() => setOpen((value) => !value)} title="Seçenekler" type="button">⋮</button>
      {open && (
        <div aria-label="Tarayıcı seçenekleri" className="browser-menu__popup" role="menu">
          <label className="browser-menu__item" role="menuitemcheckbox" aria-checked={keepCookies}>
            <input checked={keepCookies} onChange={(event) => onKeepCookies(event.target.checked)} type="checkbox" />
            <span>Keep cookies <small>çerezleri oturumlar arasında sakla</small></span>
          </label>
          <button className="browser-menu__item" onClick={() => { setOpen(false); onClearData(); }} role="menuitem" type="button">
            Clear browsing data <small>çerez ve site verisini sil</small>
          </button>
          <label className="browser-menu__item" role="menuitemcheckbox" aria-checked={autoVerify === true}>
            <input checked={autoVerify === true} disabled={autoVerify === null} onChange={(event) => void toggleAutoVerify(event.target.checked)} type="checkbox" />
            <span>Auto-verify changes <small>.claude/launch.json autoVerify</small></span>
          </label>
          <label className="browser-menu__item" role="menuitemcheckbox" aria-checked={openLinks}>
            <input checked={openLinks} onChange={(event) => { saveOpenLinksInside(event.target.checked); setOpenLinks(event.target.checked); }} type="checkbox" />
            <span>Open links in built-in browser <small>sohbetteki bağlantılar burada açılır</small></span>
          </label>
          {error && <p className="browser-menu__error" role="alert">{error}</p>}
        </div>
      )}
    </div>
  );
}

/** Dev servers menüsü (#439): launch.json sunucularını başlat, durdur, hepsini durdur. */
export function DevServersMenu({ client, onStarted }: { client: ProtocolClient; onStarted: (url: string) => void }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<LaunchConfigRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);

  const load = useCallback(async () => {
    const payload = await client.request("onizleme.yapilandirmalar", {}).catch(() => null);
    if (!payload) return;
    setRows(decodeRows(payload));
    setError(payload.ok === false && typeof payload.metin === "string" ? payload.metin : "");
  }, [client]);

  useEffect(() => { if (open) void load(); }, [open, load]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : "İşlem yapılamadı."); }
    finally { setBusy(false); await load(); }
  };
  const start = (row: LaunchConfigRow) => run(async () => {
    if (row.guvenGerekli) await client.request("onizleme.guven", {});
    const payload = await client.request("onizleme.baslat", { ad: row.ad });
    if (payload.ok !== true || typeof payload.url !== "string") throw new Error(typeof payload.metin === "string" ? payload.metin : "Sunucu başlatılamadı.");
    onStarted(payload.url);
  });
  const stop = (row: LaunchConfigRow) => run(async () => { await client.request("onizleme.durdur", { ad: row.ad }); });
  const stopAll = () => run(async () => {
    for (const row of rows.filter((item) => item.calisiyor)) await client.request("onizleme.durdur", { ad: row.ad });
  });

  return (
    <div className="browser-menu" ref={ref}>
      <button aria-expanded={open} aria-haspopup="menu" aria-label="Dev servers" onClick={() => setOpen((value) => !value)} title="Dev servers" type="button">▶︎</button>
      {open && (
        <div aria-label="Dev servers" className="browser-menu__popup" role="menu">
          {rows.length === 0 && <p className="browser-menu__empty">.claude/launch.json'da sunucu yok.</p>}
          {rows.map((row) => (
            <div className="browser-menu__server" key={row.ad}>
              <span title={row.komut}>{row.ad}{row.calisiyor ? " · çalışıyor" : ""}</span>
              {row.calisiyor
                ? <button disabled={busy} onClick={() => void stop(row)} type="button">Durdur</button>
                : <button disabled={busy} onClick={() => void start(row)} type="button">{row.guvenGerekli ? "Güven ve başlat" : "Başlat"}</button>}
            </div>
          ))}
          {rows.some((row) => row.calisiyor) && (
            <button className="browser-menu__item" disabled={busy} onClick={() => void stopAll()} role="menuitem" type="button">Hepsini durdur</button>
          )}
          {error && <p className="browser-menu__error" role="alert">{error}</p>}
        </div>
      )}
    </div>
  );
}
