import { useEffect, useMemo, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./SkillVisibilityPanel.css";

/** Claude Code `skillOverrides` değerleri; döngü sırası `/skills` panelindekiyle aynı. */
export const VISIBILITY_LABELS: Record<string, string> = {
  on: "on · ad ve açıklama",
  "name-only": "name-only · yalnız ad",
  "user-invocable-only": "user-invocable-only · yalnız /ad",
  off: "off · kapalı",
};

interface VisibilityRow {
  ad: string;
  kaynak: string;
  aciklama: string;
  gorunurluk: string;
  belirtec: number;
}

function rowsFrom(payload: Record<string, unknown>): VisibilityRow[] {
  if (payload.ok !== true) throw new Error(String(payload.hata ?? payload.metin ?? "Beceri listesi alınamadı."));
  const raws = Array.isArray(payload.beceriler) ? payload.beceriler : [];
  return raws.flatMap((raw) => {
    if (!raw || typeof raw !== "object") return [];
    const row = raw as Record<string, unknown>;
    if (typeof row.ad !== "string" || typeof row.gorunurluk !== "string") return [];
    return [{
      ad: row.ad,
      kaynak: typeof row.kaynak === "string" ? row.kaynak : "",
      aciklama: typeof row.aciklama === "string" ? row.aciklama : "",
      gorunurluk: row.gorunurluk,
      belirtec: typeof row.belirtec === "number" ? row.belirtec : 0,
    }];
  });
}

/**
 * Masaüstü `/skills` paneli (Claude Code #176): bütün beceriler (kapalılar dahil, eklenti
 * becerileri hariç) görünürlük ve liste maliyetiyle. Yazmak süzer, "Token sırası" maliyete
 * göre sıralar, görünürlük düğmesi `on → name-only → user-invocable-only → off` döndürür ve
 * `.claude/settings.local.json` `skillOverrides`'a hemen kaydeder (`yetenek.gorunurluk`).
 */
export function SkillVisibilityPanel({ client, onChanged }: { client: ProtocolClient; onChanged?: () => void }) {
  const [rows, setRows] = useState<VisibilityRow[]>([]);
  const [query, setQuery] = useState("");
  const [byTokens, setByTokens] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    void client.request("yetenek.gorunurluk_listesi", {}).then((payload) => {
      if (!active) return;
      setRows(rowsFrom(payload));
      setLoaded(true);
    }).catch((reason) => active && setError(String(reason)));
    return () => { active = false; };
  }, [client]);

  const visible = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("tr");
    const matched = rows.filter((row) => !term || `${row.ad} ${row.aciklama}`.toLocaleLowerCase("tr").includes(term));
    return byTokens ? [...matched].sort((a, b) => b.belirtec - a.belirtec) : matched;
  }, [rows, query, byTokens]);

  const cycle = (row: VisibilityRow) => {
    void client.request("yetenek.gorunurluk", { ad: row.ad }).then((payload) => {
      if (payload.ok !== true) throw new Error(String(payload.hata ?? payload.metin ?? "Görünürlük değiştirilemedi."));
      const value = String(payload.gorunurluk ?? row.gorunurluk);
      setRows((current) => current.map((entry) => entry.ad === row.ad ? { ...entry, gorunurluk: value } : entry));
      setNotice(String(payload.metin ?? `${row.ad}: ${value}`));
      onChanged?.();
    }).catch((reason) => setError(String(reason)));
  };

  return (
    <section aria-label="Beceri görünürlüğü" className="skill-visibility">
      <div className="skill-visibility__toolbar">
        <input aria-label="Becerileri süz" onChange={(event) => setQuery(event.target.value)} placeholder="Süz" type="search" value={query} />
        <button aria-pressed={byTokens} onClick={() => setByTokens((value) => !value)} title="Liste maliyetine göre sırala (/skills t)" type="button">Token sırası</button>
      </div>
      <p className="skill-visibility__hint">Görünürlük düğmesi değeri döndürür ve projenin <code>.claude/settings.local.json</code> dosyasındaki <code>skillOverrides</code> alanına kaydeder.</p>
      {error && <p className="skill-visibility__error" role="alert">{error}</p>}
      {loaded && visible.length === 0 && <p className="skill-visibility__empty">Eşleşen beceri yok.</p>}
      <ul className="skill-visibility__list">
        {visible.map((row) => (
          <li className="skill-visibility__row" data-visibility={row.gorunurluk} key={row.ad}>
            <span className="skill-visibility__name"><strong>{row.ad}</strong><small>{row.kaynak} · ~{row.belirtec} belirteç</small></span>
            <span className="skill-visibility__desc">{row.aciklama || "Açıklama sağlanmamış."}</span>
            <button aria-label={`${row.ad} görünürlüğü: ${row.gorunurluk}`} className="skill-visibility__pill" onClick={() => cycle(row)} type="button">{VISIBILITY_LABELS[row.gorunurluk] ?? row.gorunurluk}</button>
          </li>
        ))}
      </ul>
      {notice && <p aria-live="polite" className="skill-visibility__notice">{notice}</p>}
    </section>
  );
}
