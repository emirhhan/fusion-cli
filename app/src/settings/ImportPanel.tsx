import { useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import "./ImportPanel.css";

/**
 * Başka araçtan içe aktar (P-071) — Claude Code `/import` karşılığı.
 *
 * Kaynak seçilir, önce önizleme gelir (ne eklenecek, ne zaten var, ne zaten okunuyor, ne neden
 * atlandı); "İçe aktar" yalnız "eklenecek" satırları yazar. Sır değerleri hiçbir satırda
 * görünmez; şifreli depoya gider. Terminalde `/import <kaynak>` ve `fusion import` aynı işi yapar.
 */

const SOURCES: { id: string; label: string }[] = [
  { id: "claude", label: "Claude Code" },
  { id: "codex", label: "Codex" },
  { id: "gemini", label: "Gemini CLI" },
  { id: "cursor", label: "Cursor" },
];

interface ImportRow { tur: string; ad: string; durum: string; ayrinti: string; dosya: string }

function rowsFrom(raw: unknown): ImportRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((row): row is Record<string, unknown> => !!row && typeof row === "object").map((row) => ({
    tur: String(row.tur ?? ""), ad: String(row.ad ?? ""), durum: String(row.durum ?? ""),
    ayrinti: String(row.ayrinti ?? ""), dosya: String(row.dosya ?? ""),
  }));
}

export function ImportPanel({ client }: { client: ProtocolClient }) {
  const [source, setSource] = useState("claude");
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const [pending, setPending] = useState(0);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const preview = async (kaynak: string, keepNotice = false) => {
    setBusy(true); setError(null);
    if (!keepNotice) setNotice("");
    try {
      const payload = await client.request("ice_aktar.onizle", { kaynak });
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Önizleme alınamadı."));
      setRows(rowsFrom(payload.ogeler));
      setPending(typeof payload.eklenecek === "number" ? payload.eklenecek : 0);
      setWarnings(Array.isArray(payload.uyarilar) ? payload.uyarilar.map(String) : []);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  };

  const apply = async () => {
    setBusy(true); setError(null);
    try {
      const payload = await client.request("ice_aktar.uygula", { kaynak: source });
      // Plan kurulamadıysa (`{ok:false, metin}`) "0 öğe aktarıldı" denmez; neden gösterilir.
      if (payload.ok !== true && !Array.isArray(payload.hatalar)) throw new Error(String(payload.metin ?? "İçe aktarılamadı."));
      const failures = Array.isArray(payload.hatalar) ? payload.hatalar as { ad?: unknown; neden?: unknown }[] : [];
      const failed = failures.map((item) => `${String(item.ad ?? "")}: ${String(item.neden ?? "")}`);
      setNotice(`İçe aktarıldı: ${String(payload.uygulanan ?? 0)} öğe. MCP sunucuları Fusion yeniden başlayınca bağlanır.`);
      if (failed.length > 0) setError(failed.join(" · "));
      setBusy(false);
      await preview(source, true);
    } catch (reason) { setError(errorMessage(reason)); setBusy(false); }
  };

  return <article id="settings-import" className="settings__card">
    <h3>Başka araçtan içe aktar</h3>
    <p className="settings__hint">MCP sunucuları, izin kuralları, özel komutlar ve kurallar Fusion'a taşınır. CLAUDE.md, AGENTS.md, <code>.mcp.json</code> ve beceri klasörleri zaten doğrudan okunur. Terminalde <code>/import</code>.</p>
    <div className="settings__actions" role="group" aria-label="İçe aktarma kaynağı">
      {SOURCES.map((item) => (
        <button aria-pressed={source === item.id} disabled={busy} key={item.id} onClick={() => { setSource(item.id); void preview(item.id); }} type="button">{item.label}</button>
      ))}
    </div>
    {error && <p className="settings__inline-error" role="alert"><span>{error}</span></p>}
    {rows && rows.length === 0 && warnings.length === 0 && <p className="settings__hint">Bu kaynakta taşınacak yapılandırma bulunamadı.</p>}
    {rows && rows.length > 0 && (
      <table aria-label="İçe aktarma önizlemesi" className="settings__table">
        <thead><tr><th>Tür</th><th>Ad</th><th>Durum</th><th>Ayrıntı</th></tr></thead>
        <tbody>{rows.map((row) => <tr data-status={row.durum} key={`${row.tur}:${row.ad}:${row.dosya}`}><td>{row.tur}</td><td>{row.ad}</td><td>{row.durum}</td><td title={row.dosya}>{row.ayrinti}</td></tr>)}</tbody>
      </table>
    )}
    {warnings.map((warning) => <p className="settings__hint" key={warning}>{warning}</p>)}
    {rows && (
      <div className="settings__actions">
        <button disabled={busy || pending === 0} onClick={() => void apply()} type="button">{pending > 0 ? `İçe aktar (${pending})` : "Yeni bir şey yok"}</button>
      </div>
    )}
    {notice && <p aria-live="polite" className="settings__hint">{notice}</p>}
  </article>;
}
