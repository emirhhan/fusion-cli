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

/** "claude+codex" → "Claude · Codex". Köşeli parantezli ham kaynak adı teknik duruyordu. */
function sourceLabels(source: string): string {
  return source.split("+").map((value) => value.charAt(0).toLocaleUpperCase("tr-TR") + value.slice(1)).join(" · ");
}

const kindLabels: Record<CapabilityKind, string> = {
  beceri: "Beceri", ajan: "Ajan", talimat: "Proje talimatı", mcp: "MCP",
};

/** Sekme sırası: ChatGPT'deki gibi tür başına filtre. */
const KIND_TABS: [CapabilityKind | "tümü", string][] = [
  ["tümü", "Tümü"], ["beceri", "Beceriler"], ["ajan", "Ajanlar"], ["talimat", "Talimatlar"], ["mcp", "MCP"],
];

/** Kart simgesi: adın ilk harfi, türe göre tonlanmış kare. */
function SkillAvatar({ item }: { item: CatalogItem }) {
  return <span aria-hidden="true" className="skills-catalog__avatar" data-kind={item.tur}>{item.ad.charAt(0).toLocaleUpperCase("tr-TR")}</span>;
}

export function SkillsCatalog({ client, onClose }: { client: ProtocolClient; onClose: () => void }) {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<CapabilityKind | "tümü">("tümü");
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

  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase("tr");
    return items.filter((item) =>
      (kind === "tümü" || item.tur === kind) &&
      (!term || `${item.ad} ${item.aciklama} ${item.kaynak}`.toLocaleLowerCase("tr").includes(term)),
    );
  }, [items, query, kind]);
  // Etkin olanlar üstte: kullanıcı varsayılan açık becerileri ilk bakışta görür
  // (OmniRoute/Hermes'teki "aktif beceriler" listesi gibi).
  const etkinler = filtered.filter((item) => item.etkin && item.tur !== "talimat");
  const digerleri = filtered.filter((item) => !(item.etkin && item.tur !== "talimat"));

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

  const kart = (item: CatalogItem) => (
    <article className="skills-catalog__card" data-enabled={item.etkin} key={`${item.tur}:${item.ad}`} data-selected={selected?.tur === item.tur && selected.ad === item.ad}>
      <button aria-label={`${item.ad} ayrıntılarını aç`} className="skills-catalog__row" onClick={() => open(item)} type="button">
        <SkillAvatar item={item} />
        <span className="skills-catalog__summary">
          <strong>{item.ad}</strong>
          <span>{item.aciklama || "Açıklama sağlanmamış."}</span>
          <small>{kindLabels[item.tur]} · {sourceLabels(item.kaynak)}</small>
        </span>
      </button>
      {item.tur !== "talimat" && <button aria-checked={item.etkin} aria-label={`${item.ad} oturum etkinliği`} className="skills-catalog__switch" onClick={() => toggle(item)} role="switch" type="button"><span /></button>}
    </article>
  );

  return (
    <main className="skills-catalog">
      <header className="skills-catalog__header">
        <div><h2>Beceriler</h2><p>Fusion'ın bu çalışma alanında kullandığı beceriler, ajanlar, proje talimatları ve MCP araçları. Claude, Codex ve Hermes'ten gelenler de burada.</p></div>
        <button aria-label="Kataloğu kapat" onClick={onClose} type="button">Kapat</button>
      </header>
      <div className="skills-catalog__toolbar">
        <input aria-label="Beceri ve ajan ara" onChange={(event) => setQuery(event.target.value)} placeholder="Beceri ara" type="search" value={query} />
        <div aria-label="Türe göre filtrele" className="skills-catalog__tabs" role="tablist">
          {KIND_TABS.map(([value, label]) => <button aria-selected={kind === value} key={value} onClick={() => setKind(value)} role="tab" type="button">{label}</button>)}
        </div>
      </div>
      {error && <p className="skills-catalog__error" role="alert">{error}</p>}
      <div className="skills-catalog__layout">
        <section aria-label="Yetenek kataloğu" className="skills-catalog__list">
          {filtered.length === 0 && <p className="skills-catalog__empty">Eşleşen öğe yok.</p>}
          {etkinler.length > 0 && <h3 className="skills-catalog__group">Etkin · {etkinler.length}</h3>}
          {etkinler.length > 0 && <div className="skills-catalog__grid">{etkinler.map(kart)}</div>}
          {digerleri.length > 0 && <h3 className="skills-catalog__group">{etkinler.length > 0 ? "Diğerleri" : "Tümü"}</h3>}
          {digerleri.length > 0 && <div className="skills-catalog__grid">{digerleri.map(kart)}</div>}
        </section>
        <aside aria-label="Yetenek ayrıntısı" className="skills-catalog__detail">
          {selected ? <><div className="skills-catalog__detail-head"><SkillAvatar item={selected} /><div><h2>{selected.ad}</h2><span>{kindLabels[selected.tur]} · {sourceLabels(selected.kaynak)}{selected.izinler.length > 0 ? ` · ${selected.izinler.join(", ")}` : ""}</span></div></div><pre>{detail || "Yükleniyor…"}</pre>{selected.tur !== "talimat" && <button disabled={!selected.etkin} onClick={() => useNext(selected)} type="button">Bu {selected.tur === "beceri" ? "beceriyi" : selected.tur === "ajan" ? "ajanı" : "MCP'yi"} sonraki turda kullan</button>}{notice && <p aria-live="polite">{notice}</p>}</> : <p>Ne yaptığını, nereden geldiğini ve hangi izinleri kullandığını görmek için bir beceri seç.</p>}
        </aside>
      </div>
    </main>
  );
}
