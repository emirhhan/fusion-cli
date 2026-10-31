import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";

/**
 * Kullanım ve sağlık özeti.
 *
 * Rakamlar UYDURULMAZ: token ve maliyet sağlayıcı sınırında hesaplanıp
 * çekirdekte toplanır, güvenilirlik ölçülen çağrılardan gelir. Sayaç OTURUM
 * ÖMÜRLÜDÜR; "Son dönem" ve "Kim harcadı" bölümleri çekirdeğin kalıcı kullanım
 * günlüğünden gelir (yalnız sayılar, istem metni yok; `runtime.usage_log`).
 */

interface UsageRow {
  cagri: number;
  cikti_token: number;
  girdi_token: number;
  maliyet_usd: number;
  modeller: { maliyet_usd: number; model: string; toplam_token: number }[];
  toplam_token: number;
}

interface HealthRow {
  durum: string;
  gecikme_ms: number;
  model: string;
  ornek: number;
  skor: number;
}

/** Kalıcı günlükten gelen pencere satırı (24 saat / 7 gün / 30 gün). */
interface HistoryRow {
  cagri: number;
  maliyet_tam: boolean;
  maliyet_usd: number;
  pencere: string;
  toplam_token: number;
}

interface AttributionRow {
  ad: string;
  cagri: number;
  maliyet_usd?: number;
  toplam_token?: number;
}

interface Attribution {
  beceriler: AttributionRow[];
  kaynaklar: AttributionRow[];
  mcp: AttributionRow[];
  pencere?: string;
}

const sayi = (value: number) => value.toLocaleString("tr-TR");

export function UsagePanel({ client }: { client: ProtocolClient }) {
  const [usage, setUsage] = useState<UsageRow | null>(null);
  const [health, setHealth] = useState<HealthRow[]>([]);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [attribution, setAttribution] = useState<Attribution | null>(null);
  // Eski çekirdek alanı göndermez (undefined): o durumda kapalı notu gösterilmez.
  const [logDisabled, setLogDisabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const veri = (await client.request("kullanim.durum", {})) as {
        metin?: string;
        ok?: boolean;
        kullanim?: UsageRow;
        saglik?: HealthRow[];
        gecmis?: HistoryRow[];
        atif?: Attribution;
        gunluk_acik?: boolean;
      };
      if (!veri?.ok || !veri.kullanim) {
        setError(veri?.metin ?? "Kullanım bilgisi alınamadı.");
        return;
      }
      setUsage(veri.kullanim);
      setHealth(veri.saglik ?? []);
      setHistory(veri.gecmis ?? []);
      setAttribution(veri.atif ?? null);
      setLogDisabled(veri.gunluk_acik === false);
    } catch (reason) {
      // Gerçek neden atılmaz (U2-57).
      setError(`Kullanım bilgisi alınamadı. Neden: ${errorMessage(reason)}`);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <article className="settings__card settings__card--wide">
      <h3>Bu oturumdaki kullanım</h3>
      {/* Sayaç yalnız açılışta yükleniyordu; elle yenilenebilir (U2-57). */}
      {!loading && !error && <button className="settings__error-retry" onClick={() => void load()} type="button">Yenile</button>}
      {loading ? (
        <p aria-live="polite" className="settings__hint">Kullanım bilgisi okunuyor…</p>
      ) : error ? (
        <div className="settings__inline-error" role="alert">
          <span>{error}</span>
          <button onClick={() => void load()} type="button">Yeniden dene</button>
        </div>
      ) : usage && usage.cagri > 0 ? (
        <>
          <dl className="settings__pairs">
            <dt>Model çağrısı</dt>
            <dd>{sayi(usage.cagri)}</dd>
            <dt>Token</dt>
            <dd>
              {sayi(usage.toplam_token)} ({sayi(usage.girdi_token)} girdi ·{" "}
              {sayi(usage.cikti_token)} çıktı)
            </dd>
            <dt>Tahmini maliyet</dt>
            <dd>
              {usage.maliyet_usd > 0
                ? `$${usage.maliyet_usd.toFixed(4)}`
                : "Hesaplanan maliyet · $0"}
            </dd>
          </dl>
          {usage.modeller.length > 0 && (
            <ul className="settings__list">
              {usage.modeller.map((row) => (
                <li key={row.model}>
                  <strong>{row.model}</strong>
                  <code>{sayi(row.toplam_token)} token</code>
                  <span>{row.maliyet_usd > 0 ? `$${row.maliyet_usd.toFixed(4)}` : "$0"}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="settings__hint">Bu oturumda henüz model çağrısı yapılmadı.</p>
      )}

      {/* Kalıcı günlük (P-056): oturum sayacından AYRI veri; günlük kapalıysa bölüm gizli
          ve nedeni söylenir (eskiden sessizce kayboluyordu). */}
      {!loading && !error && logDisabled && (
        <p className="settings__hint">
          Kullanım günlüğü kapalı (<code>runtime.usage_log: false</code>); son dönem ve kim
          harcadı bölümleri yalnız günlük açıkken dolar.
        </p>
      )}
      {!loading && !error && history.length > 0 && (
        <>
          <h3 className="settings__section-title">Son dönem</h3>
          <ul className="settings__list">
            {history.map((row) => (
              <li key={row.pencere}>
                <strong>{row.pencere}</strong>
                <code>{sayi(row.cagri)} çağrı · {sayi(row.toplam_token)} token</code>
                <span>{row.maliyet_tam ? "" : "en az "}${row.maliyet_usd.toFixed(4)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {!loading && !error && attribution && (attribution.kaynaklar.length > 0 || attribution.mcp.length > 0 || attribution.beceriler.length > 0) && (
        <>
          <h3 className="settings__section-title">Kim harcadı{attribution.pencere ? ` (${attribution.pencere})` : ""}</h3>
          <ul className="settings__list">
            {attribution.kaynaklar.map((row) => (
              <li key={`k:${row.ad}`}>
                <strong>{row.ad}</strong>
                <code>{sayi(row.cagri)} çağrı · {sayi(row.toplam_token ?? 0)} token</code>
                <span>${(row.maliyet_usd ?? 0).toFixed(4)}</span>
              </li>
            ))}
            {attribution.mcp.map((row) => (
              <li key={`m:${row.ad}`}>
                <strong>MCP · {row.ad}</strong>
                <code>{sayi(row.cagri)} araç çağrısı</code>
                <span />
              </li>
            ))}
            {attribution.beceriler.map((row) => (
              <li key={`b:${row.ad}`}>
                <strong>Beceri · {row.ad}</strong>
                <code>{sayi(row.cagri)} yükleme</code>
                <span />
              </li>
            ))}
          </ul>
        </>
      )}

      <h3 className="settings__section-title">Model sağlığı</h3>
      {!loading && !error && health.length > 0 ? (
        <ul className="settings__list">
          {health.map((row) => (
            <li key={row.model}>
              <strong>{row.model}</strong>
              <code>
                {row.durum} · %{Math.round(row.skor * 100)} · {sayi(row.gecikme_ms)} ms
              </code>
              <span>{sayi(row.ornek)} örnek</span>
            </li>
          ))}
        </ul>
      ) : !loading && !error ? (
        <p className="settings__hint">
          Henüz ölçüm yok. Sağlık, gerçek çağrılardan toplanır; ölçülmemiş bir modeli
          kötü göstermemek için boş bırakılır.
        </p>
      ) : null}
    </article>
  );
}
