import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

/**
 * Önizleme sayfasının konsol ve ağ günlüğü (P-041).
 *
 * Ölçüldü (31 Ekim): iframe ayrı kökenli; ana pencere konsolunu okuyamıyor. Günlük,
 * çekirdeğin başsız tarayıcısıyla (`onizleme.gunluk`) o anın fotoğrafı olarak alınır
 * — Claude Code'un `read_console_messages` / `read_network_requests` karşılığı. Canlı
 * akış değildir; "Yenile" yeni bir ölçüm yapar.
 */
export interface ConsoleRow { seviye: string; metin: string; kaynak: string }
export interface NetworkRow { yontem: string; url: string; durum: number; tur: string; hata: string; basarisiz: boolean }

export interface PageLogResult {
  konsol: ConsoleRow[];
  ag: NetworkRow[];
  hataSayisi: number;
  basarisizIstek: number;
}

export function decodePageLog(payload: Record<string, unknown>): PageLogResult {
  if (payload.ok !== true) {
    throw new Error(typeof payload.metin === "string" && payload.metin ? payload.metin : "Günlük alınamadı.");
  }
  const konsol = (Array.isArray(payload.konsol) ? payload.konsol : []).flatMap((item) => {
    const row = item as Record<string, unknown>;
    if (!row || typeof row.metin !== "string") return [];
    return [{
      seviye: typeof row.seviye === "string" ? row.seviye : "log",
      metin: row.metin,
      kaynak: typeof row.kaynak === "string" ? row.kaynak : "",
    }];
  });
  const ag = (Array.isArray(payload.ag) ? payload.ag : []).flatMap((item) => {
    const row = item as Record<string, unknown>;
    if (!row || typeof row.url !== "string") return [];
    return [{
      yontem: typeof row.yontem === "string" ? row.yontem : "GET",
      url: row.url,
      durum: typeof row.durum === "number" ? row.durum : 0,
      tur: typeof row.tur === "string" ? row.tur : "",
      hata: typeof row.hata === "string" ? row.hata : "",
      basarisiz: row.basarisiz === true,
    }];
  });
  return {
    konsol,
    ag,
    hataSayisi: typeof payload.hata_sayisi === "number" ? payload.hata_sayisi : 0,
    basarisizIstek: typeof payload.basarisiz_istek === "number" ? payload.basarisiz_istek : 0,
  };
}

export interface PreviewLogProps {
  client: ProtocolClient;
  url: string;
  onClose: () => void;
  /** Günlüğü veren istek: önizleme için o anın ölçümü, Tarayıcı panelinde (P-045) canlı birikim. */
  rpc?: string;
}

type LogTab = "konsol" | "ag";

export function PreviewLog({ client, url, onClose, rpc = "onizleme.gunluk" }: PreviewLogProps) {
  const [tab, setTab] = useState<LogTab>("konsol");
  const [result, setResult] = useState<PageLogResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [run, setRun] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void client.request(rpc, { url })
      .then((payload) => { if (active) setResult(decodePageLog(payload)); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [client, url, run, rpc]);

  const konsol = result?.konsol.filter((row) => !onlyProblems || ["error", "pageerror", "warning"].includes(row.seviye)) ?? [];
  const ag = result?.ag.filter((row) => !onlyProblems || row.basarisiz) ?? [];

  return (
    <section aria-label="Önizleme günlüğü" className="preview-log" data-testid="preview-log">
      <header className="preview-log__bar">
        <div aria-label="Günlük türü" className="preview-log__tabs" role="tablist">
          <button aria-selected={tab === "konsol"} onClick={() => setTab("konsol")} role="tab" type="button">
            Konsol{result ? ` (${result.konsol.length}${result.hataSayisi ? ` · ${result.hataSayisi} hata` : ""})` : ""}
          </button>
          <button aria-selected={tab === "ag"} onClick={() => setTab("ag")} role="tab" type="button">
            Ağ{result ? ` (${result.ag.length}${result.basarisizIstek ? ` · ${result.basarisizIstek} başarısız` : ""})` : ""}
          </button>
        </div>
        <label className="preview-log__filter">
          <input checked={onlyProblems} onChange={(event) => setOnlyProblems(event.target.checked)} type="checkbox" />
          Yalnız sorunlar
        </label>
        <button aria-label="Günlüğü yenile" disabled={loading} onClick={() => setRun((n) => n + 1)} title="Yeniden ölç" type="button">↻</button>
        <button aria-label="Günlüğü kapat" onClick={onClose} title="Kapat" type="button">×</button>
      </header>
      {loading ? (
        <p className="preview-log__status" role="status">Sayfa başsız tarayıcıda açılıyor…</p>
      ) : error ? (
        <p className="preview-log__status preview-log__status--error" role="alert">{error}</p>
      ) : tab === "konsol" ? (
        konsol.length === 0 ? (
          <p className="preview-log__status">{onlyProblems ? "Hata ya da uyarı yok." : "Konsolda mesaj yok."}</p>
        ) : (
          <ol className="preview-log__list">
            {konsol.map((row, index) => (
              <li className={`preview-log__row preview-log__row--${row.seviye}`} key={`${index}-${row.metin}`}>
                <span className="preview-log__level">{row.seviye}</span>
                <span className="preview-log__text">{row.metin}</span>
                {row.kaynak && <span className="preview-log__source">{row.kaynak}</span>}
              </li>
            ))}
          </ol>
        )
      ) : ag.length === 0 ? (
        <p className="preview-log__status">{onlyProblems ? "Başarısız istek yok." : "Ağ isteği kaydedilmedi."}</p>
      ) : (
        <ol className="preview-log__list">
          {ag.map((row, index) => (
            <li className={`preview-log__row${row.basarisiz ? " preview-log__row--error" : ""}`} key={`${index}-${row.url}`}>
              <span className="preview-log__level">{row.durum || "—"}</span>
              <span className="preview-log__text">{row.yontem} {row.url}</span>
              <span className="preview-log__source">{row.hata || row.tur}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
