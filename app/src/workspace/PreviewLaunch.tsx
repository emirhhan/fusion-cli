import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

/**
 * Önizleme panelinden dev sunucu başlatma (`.fusion/launch.json`, P-041).
 *
 * Ölçüldü (31 Ekim): kullanıcı sunucuyu terminalde kendisi başlatıp adresi elle yazmak
 * zorundaydı. Claude Code'un `preview_start --name` akışı gibi: yapılandırma seçilir,
 * "Başlat" çekirdekte `onizleme.baslat` çağırır, dönen adres panelde açılır. Komut
 * metni seçicide görünür ki kullanıcı neyi çalıştırdığını bilsin.
 */
export interface LaunchConfigRow {
  ad: string;
  komut: string;
  url: string;
  baglan: boolean;
  calisiyor: boolean;
}

export interface PreviewLaunchProps {
  client: ProtocolClient;
  /** Sunucu açılınca panelde gösterilecek adres. */
  onStarted: (url: string) => void;
  disabled?: boolean;
}

function decodeRows(payload: Record<string, unknown>): LaunchConfigRow[] {
  const raw = Array.isArray(payload.yapilandirmalar) ? payload.yapilandirmalar : [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    if (typeof row.ad !== "string" || typeof row.url !== "string") return [];
    return [{
      ad: row.ad,
      komut: typeof row.komut === "string" ? row.komut : "",
      url: row.url,
      baglan: row.baglan === true,
      calisiyor: row.calisiyor === true,
    }];
  });
}

export function PreviewLaunch({ client, onStarted, disabled = false }: PreviewLaunchProps) {
  const [rows, setRows] = useState<LaunchConfigRow[]>([]);
  const [selected, setSelected] = useState("");
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const payload = await client.request("onizleme.yapilandirmalar", {});
      // Eski çekirdek bu isteği tanımaz ya da başka bir yanıt döner: başlatıcı sessizce gizlenir,
      // panelin kendisi (adres çubuğu, iframe) etkilenmez.
      if (!payload || typeof payload !== "object" || !("yapilandirmalar" in payload)) return;
      const next = decodeRows(payload);
      setRows(next);
      setSource(typeof payload.kaynak === "string" ? payload.kaynak : null);
      setError(payload.ok === false && typeof payload.metin === "string" ? payload.metin : null);
      setSelected((current) => (next.some((row) => row.ad === current) ? current : next[0]?.ad ?? ""));
    } catch {
      // Çekirdek yanıt vermedi: başlatıcı görünmez kalır.
    }
  }, [client]);

  useEffect(() => { void load(); }, [load]);

  const current = rows.find((row) => row.ad === selected) ?? null;

  const start = async () => {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      const payload = await client.request("onizleme.baslat", { ad: current.ad });
      if (payload.ok !== true || typeof payload.url !== "string") {
        setError(typeof payload.metin === "string" ? payload.metin : "Sunucu başlatılamadı.");
        return;
      }
      onStarted(payload.url);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sunucu başlatılamadı.");
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!current) return;
    setBusy(true);
    try {
      await client.request("onizleme.durdur", { ad: current.ad });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sunucu durdurulamadı.");
    } finally {
      setBusy(false);
    }
  };

  if (rows.length === 0 && !error) return null;

  return (
    <div className="preview-launch" data-testid="preview-launch">
      {rows.length > 0 && (
        <>
          <label className="preview-panel__sr-only" htmlFor="preview-launch-config">Dev sunucu yapılandırması</label>
          <select
            disabled={disabled || busy}
            id="preview-launch-config"
            onChange={(event) => setSelected(event.target.value)}
            title={source ? `${source} içindeki yapılandırmalar` : undefined}
            value={selected}
          >
            {rows.map((row) => (
              <option key={row.ad} value={row.ad}>
                {row.calisiyor ? "● " : ""}{row.ad}{row.komut ? ` — ${row.komut}` : " — bağlan"}
              </option>
            ))}
          </select>
          {current?.calisiyor && !current.baglan ? (
            <button disabled={disabled || busy} onClick={() => void stop()} type="button">Durdur</button>
          ) : (
            <button disabled={disabled || busy || !current} onClick={() => void start()} type="button">
              {busy ? "Başlatılıyor…" : current?.calisiyor ? "Aç" : "Başlat"}
            </button>
          )}
        </>
      )}
      {error && <p className="preview-panel__address-error" role="alert">{error}</p>}
    </div>
  );
}
