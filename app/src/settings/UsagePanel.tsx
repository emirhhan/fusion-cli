import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";

/**
 * Kullanım ve sağlık özeti.
 *
 * Rakamlar UYDURULMAZ: token ve maliyet sağlayıcı sınırında hesaplanıp
 * çekirdekte toplanır, güvenilirlik ölçülen çağrılardan gelir. Sayaç OTURUM
 * ÖMÜRLÜDÜR; kalıcı bir kullanım geçmişi tutulmaz.
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

/**
 * Kota/limit göstergesi (P-066). Claude Code'un plan çubuklarının Fusion karşılığı:
 * abonelik kotası sağlayıcı tarafından bildirilmez, UYDURULMAZ; yalnız ayarlanan
 * dakikalık sınır ve ölçülen "sağlayıcı bekletiyor" (429 serisi) gösterilir.
 */
interface LimitsRow {
  dakikaLimitleri: { saglayici: string; dakikaLimiti: number }[];
  kotaBekleyen: { model: string; seri: number; yenidenSn: number }[];
}

const BOS_LIMITLER: LimitsRow = { dakikaLimitleri: [], kotaBekleyen: [] };

const sayi = (value: number) => value.toLocaleString("tr-TR");

export function UsagePanel({ client }: { client: ProtocolClient }) {
  const [usage, setUsage] = useState<UsageRow | null>(null);
  const [health, setHealth] = useState<HealthRow[]>([]);
  const [limits, setLimits] = useState<LimitsRow>(BOS_LIMITLER);
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
        limitler?: Partial<LimitsRow>;
      };
      if (!veri?.ok || !veri.kullanim) {
        setError(veri?.metin ?? "Kullanım bilgisi alınamadı.");
        return;
      }
      setUsage(veri.kullanim);
      setHealth(veri.saglik ?? []);
      // Eski çekirdek `limitler` göndermez: bölüm boş kalır, hata sayılmaz.
      setLimits({
        dakikaLimitleri: veri.limitler?.dakikaLimitleri ?? [],
        kotaBekleyen: veri.limitler?.kotaBekleyen ?? [],
      });
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

      <h3 className="settings__section-title">Hız sınırları ve kota</h3>
      {!loading && !error && (
        <>
          {limits.kotaBekleyen.length > 0 ? (
            <ul className="settings__list" aria-label="Kota bekleten modeller">
              {limits.kotaBekleyen.map((row) => (
                <li key={row.model}>
                  <strong>{row.model}</strong>
                  <code>sağlayıcı bekletiyor · {row.seri}. kez</code>
                  <span>{row.yenidenSn > 0 ? `${sayi(row.yenidenSn)} sn sonra yeniden` : "yeniden deneniyor"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="settings__hint">Şu an hiçbir sağlayıcı kota bekletmiyor.</p>
          )}
          {limits.dakikaLimitleri.length > 0 && (
            <dl className="settings__pairs" aria-label="Dakikalık istek sınırları">
              {limits.dakikaLimitleri.map((row) => (
                <div key={row.saglayici}>
                  <dt>{row.saglayici}</dt>
                  <dd>{sayi(row.dakikaLimiti)} istek/dk (bütün sekmelerde ortak)</dd>
                </div>
              ))}
            </dl>
          )}
          <p className="settings__hint">
            Abonelik kotası (ChatGPT, Claude web) sağlayıcı tarafından bildirilmez; burada yalnız
            Fusion'ın ayarladığı sınır ve sağlayıcının o an bekletmesi görünür.
          </p>
        </>
      )}
    </article>
  );
}
