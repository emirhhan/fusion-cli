import { useEffect, useMemo, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./SkillsCatalog.css";

type CapabilityKind = "beceri" | "ajan" | "talimat" | "mcp";
interface CatalogItem {
  ad: string;
  aciklama: string;
  kaynak: string;
  tur: CapabilityKind;
  etkin: boolean;
  izinler: string[];
}

function itemFrom(raw: unknown, fallbackKind: CapabilityKind): CatalogItem {
  if (!raw || typeof raw !== "object") throw new Error("Geçersiz katalog öğesi.");
  const item = raw as Record<string, unknown>;
  const kind = typeof item.tur === "string" ? item.tur : fallbackKind;
  if (
    typeof item.ad !== "string" || typeof item.kaynak !== "string" ||
    !["beceri", "ajan", "talimat", "mcp"].includes(kind) || typeof item.etkin !== "boolean"
  ) throw new Error("Geçersiz katalog öğesi.");
  return {
    ad: item.ad,
    aciklama: typeof item.aciklama === "string" ? item.aciklama : "",
    kaynak: item.kaynak,
    tur: kind as CapabilityKind,
    etkin: item.etkin,
    izinler: Array.isArray(item.izinler) ? item.izinler.filter((value): value is string => typeof value === "string") : [],
  };
}

function decode(payload: Record<string, unknown>): CatalogItem[] {
  if (payload.ok !== true) throw new Error(String(payload.metin ?? "Katalog alınamadı."));
  const groups: [string, CapabilityKind][] = [["beceriler", "beceri"], ["ajanlar", "ajan"], ["talimatlar", "talimat"], ["mcp", "mcp"]];
  return groups.flatMap(([key, kind]) => Array.isArray(payload[key]) ? payload[key].map((raw) => itemFrom(raw, kind)) : []);
}

function sourceLabels(source: string): string {
  return source.split("+").map((value) => `[${value}]`).join(" ");
}

const kindLabels: Record<CapabilityKind, string> = {
  beceri: "Beceri", ajan: "Ajan", talimat: "Proje talimatı", mcp: "MCP",
};

export function SkillsCatalog({ client, onClose }: { client: ProtocolClient; onClose: () => void }) {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("tümü");
  const [selected, setSelected] = useState<CatalogItem | null>(null);
  const [detail, setDetail] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void client.request("yetenek.katalog", {}).then((payload) => {
      if (active) setItems(decode(payload));
    }).catch((reason) => active && setError(String(reason)));
    return () => { active = false; };
  }, [client]);

  const sources = useMemo(() => Array.from(new Set(items.flatMap((item) => item.kaynak.split("+")))), [items]);
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("tr");
    return items.filter((item) =>
      (source === "tümü" || item.kaynak.split("+").includes(source)) &&
      (!term || `${item.ad} ${item.aciklama} ${item.kaynak}`.toLocaleLowerCase("tr").includes(term)),
    );
  }, [items, query, source]);

  const open = (item: CatalogItem) => {
    setSelected(item);
    setDetail("");
    setNotice("");
    void client.request("yetenek.detay", { tur: item.tur, ad: item.ad }).then((payload) => {
      if (payload.ok !== true || typeof payload.icerik !== "string") throw new Error(String(payload.metin ?? "Ayrıntı alınamadı."));
      setDetail(payload.icerik);
    }).catch((reason) => setError(String(reason)));
  };

  const toggle = (item: CatalogItem) => {
    const enabled = !item.etkin;
    void client.request("yetenek.etkinlik", { tur: item.tur, ad: item.ad, etkin: enabled }).then((payload) => {
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Durum değiştirilemedi."));
      setItems((current) => current.map((entry) => entry.tur === item.tur && entry.ad === item.ad ? { ...entry, etkin: enabled } : entry));
      setSelected((current) => current?.tur === item.tur && current.ad === item.ad ? { ...current, etkin: enabled } : current);
    }).catch((reason) => setError(String(reason)));
  };

  const useNext = (item: CatalogItem) => {
    void client.request("yetenek.kullan", { tur: item.tur, ad: item.ad }).then((payload) => {
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Yetenek seçilemedi."));
      setNotice(`${item.ad}, sonraki görev için hazır.`);
    }).catch((reason) => setError(String(reason)));
  };

  return (
    <main className="skills-catalog">
      <header className="skills-catalog__header">
        <div><span>Çalışma alanı</span><h2>Katalog</h2><p>Fusion, Claude, Codex, Hermes, proje talimatları ve bağlı MCP araçları.</p></div>
        <button aria-label="Kataloğu kapat" onClick={onClose} type="button">Kapat</button>
      </header>
      <div className="skills-catalog__toolbar">
        <input aria-label="Beceri ve ajan ara" onChange={(event) => setQuery(event.target.value)} placeholder="Ara" type="search" value={query} />
        <div aria-label="Kaynağa göre filtrele" role="group">
          {["tümü", ...sources].map((value) => <button aria-pressed={source === value} key={value} onClick={() => setSource(value)} type="button">{value === "tümü" ? "Tümü" : `[${value}]`}</button>)}
        </div>
      </div>
      {error && <p className="skills-catalog__error" role="alert">{error}</p>}
      <div className="skills-catalog__layout">
        <section aria-label="Yetenek kataloğu" className="skills-catalog__list">
          {filtered.length === 0 ? <p className="skills-catalog__empty">Eşleşen öğe yok.</p> : filtered.map((item) => (
            <article data-enabled={item.etkin} key={`${item.tur}:${item.ad}`}>
              <button aria-label={`${item.ad} ayrıntılarını aç`} className="skills-catalog__row" onClick={() => open(item)} type="button">
                <span className="skills-catalog__kind">{kindLabels[item.tur]}</span>
                <span className="skills-catalog__summary"><strong>{item.ad}</strong><small>{sourceLabels(item.kaynak)}</small><span>{item.aciklama || "Açıklama sağlanmamış."}</span></span>
                <span className="skills-catalog__permissions">{item.izinler.map((permission) => <small key={permission}>{permission}</small>)}</span>
              </button>
              {item.tur !== "talimat" && <button aria-checked={item.etkin} aria-label={`${item.ad} oturum etkinliği`} className="skills-catalog__switch" onClick={() => toggle(item)} role="switch" type="button"><span /></button>}
            </article>
          ))}
        </section>
        <aside aria-label="Yetenek ayrıntısı" className="skills-catalog__detail">
          {selected ? <><div><span>{kindLabels[selected.tur]} · {sourceLabels(selected.kaynak)}</span><h2>{selected.ad}</h2></div><pre>{detail || "Yükleniyor…"}</pre>{selected.tur !== "talimat" && <button disabled={!selected.etkin} onClick={() => useNext(selected)} type="button">Bu {selected.tur === "beceri" ? "beceriyi" : selected.tur === "ajan" ? "ajanı" : "MCP'yi"} sonraki turda kullan</button>}{notice && <p aria-live="polite">{notice}</p>}</> : <p>Kaynağını, izin kapsamını ve talimatını görmek için bir öğe seç.</p>}
        </aside>
      </div>
    </main>
  );
}
