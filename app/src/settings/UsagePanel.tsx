import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

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

const sayi = (value: number) => value.toLocaleString("tr-TR");

export function UsagePanel({ client }: { client: ProtocolClient }) {
  const [usage, setUsage] = useState<UsageRow | null>(null);
  const [health, setHealth] = useState<HealthRow[]>([]);
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
      };
      if (!veri?.ok || !veri.kullanim) {
        setError(veri?.metin ?? "Kullanım bilgisi alınamadı.");
        return;
      }
      setUsage(veri.kullanim);
      setHealth(veri.saglik ?? []);
    } catch {
      setError("Kullanım bilgisi alınamadı.");
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
    </article>
  );
}
