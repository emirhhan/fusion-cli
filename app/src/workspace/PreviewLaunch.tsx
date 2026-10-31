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
  /** Komutlu ama dosya güvenilmiyor: Başlat yerine "Güven ve başlat" sorulur. */
  guvenGerekli: boolean;
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
      guvenGerekli: row.guven_gerekli === true,
    }];
  });
}

function decodeWarnings(payload: Record<string, unknown>): string[] {
  return Array.isArray(payload.uyarilar) ? payload.uyarilar.filter((w): w is string => typeof w === "string") : [];
}

export function PreviewLaunch({ client, onStarted, disabled = false }: PreviewLaunchProps) {
  const [rows, setRows] = useState<LaunchConfigRow[]>([]);
  const [selected, setSelected] = useState("");
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  /** Port dolu olduğu için başka porta kayıldıysa (`autoPort`) çekirdeğin notu. */
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const payload = await client.request("onizleme.yapilandirmalar", {});
      // Eski çekirdek bu isteği tanımaz ya da başka bir yanıt döner: başlatıcı sessizce gizlenir,
      // panelin kendisi (adres çubuğu, iframe) etkilenmez.
      if (!payload || typeof payload !== "object" || !("yapilandirmalar" in payload)) return;
      const next = decodeRows(payload);
      setRows(next);
      setSource(typeof payload.kaynak === "string" ? payload.kaynak : null);
      setWarnings(decodeWarnings(payload));
      setError(payload.ok === false && typeof payload.metin === "string" ? payload.metin : null);
      setSelected((current) => (next.some((row) => row.ad === current) ? current : next[0]?.ad ?? ""));
    } catch {
      // Çekirdek yanıt vermedi: başlatıcı görünmez kalır.
    }
  }, [client]);

  useEffect(() => { void load(); }, [load]);

  const current = rows.find((row) => row.ad === selected) ?? null;

  const start = async (trustFirst = false) => {
    if (!current) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      if (trustFirst) {
        // Kullanıcı komut metnini seçicide gördü ve "Güven ve başlat"a bastı: dosyanın şu anki
        // karması güvene alınır (fusion trust ile aynı kayıt); sonradan değişirse güven düşer.
        const guven = await client.request("onizleme.guven", {});
        if (guven.ok !== true) {
          setError(typeof guven.metin === "string" ? guven.metin : "Dosyaya güvenilemedi.");
          return;
        }
      }
      const payload = await client.request("onizleme.baslat", { ad: current.ad });
      if (payload.ok !== true || typeof payload.url !== "string") {
        setError(typeof payload.metin === "string" ? payload.metin : "Sunucu başlatılamadı.");
        return;
      }
      if (typeof payload.not === "string" && payload.not) setNote(payload.not);
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
          ) : current?.guvenGerekli ? (
            <button
              disabled={disabled || busy}
              onClick={() => void start(true)}
              title={`${source ?? "launch.json"} güvenilir değil; bu düğme dosyanın şu anki içeriğine güvenir ve komutu çalıştırır: ${current.komut}`}
              type="button"
            >
              {busy ? "Başlatılıyor…" : "Güven ve başlat"}
            </button>
          ) : (
            <button disabled={disabled || busy || !current} onClick={() => void start()} type="button">
              {busy ? "Başlatılıyor…" : current?.calisiyor ? "Aç" : "Başlat"}
            </button>
          )}
        </>
      )}
      {current?.guvenGerekli && !current.calisiyor && (
        <p className="preview-panel__address-error preview-launch__trust" role="note">
          Bu komut indirilmiş bir dosyadan geliyor; çalıştırmadan önce oku: <code>{current.komut}</code>
        </p>
      )}
      {error && <p className="preview-panel__address-error" role="alert">{error}</p>}
      {note && <p className="preview-panel__address-error" role="status">{note}</p>}
      {warnings.map((warning) => (
        <p className="preview-panel__address-error" key={warning} role="note">{warning}</p>
      ))}
    </div>
  );
}
