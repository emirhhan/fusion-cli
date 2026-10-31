import { useEffect, useMemo, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./SkillsCatalog.css";

type CapabilityKind = "beceri" | "ajan" | "talimat" | "mcp";
interface CatalogItem {
  ad: string;
  kimlik: string;
  surum: string;
  aciklama: string;
  kaynak: string;
  tur: CapabilityKind;
  etkin: boolean;
  izinler: string[];
  /** Alt ajan tanımının ayarları (P-034): model, izin kipi, tur tavanı… Boş = miras. */
  ayarlar: Record<string, unknown>;
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
    kimlik: typeof item.kimlik === "string" ? item.kimlik : item.ad,
    surum: typeof item.surum === "string" ? item.surum : "",
    aciklama: typeof item.aciklama === "string" ? item.aciklama : "",
    kaynak: item.kaynak,
    tur: kind as CapabilityKind,
    etkin: item.etkin,
    izinler: Array.isArray(item.izinler) ? item.izinler.filter((value): value is string => typeof value === "string") : [],
    ayarlar: item.ayarlar && typeof item.ayarlar === "object" && !Array.isArray(item.ayarlar) ? (item.ayarlar as Record<string, unknown>) : {},
  };
}

/**
 * Ölçüldü (29 Ekim, U6-04): tek bozuk öğe `throw` edip bütün kataloğu düşürüyordu.
 * Geçerli öğeler gösterilir, atlanan bozuk öğe sayısı döner.
 */
function decode(payload: Record<string, unknown>): { items: CatalogItem[]; skipped: number } {
  if (payload.ok !== true) throw new Error(String(payload.metin ?? "Katalog alınamadı."));
  const groups: [string, CapabilityKind][] = [["beceriler", "beceri"], ["ajanlar", "ajan"], ["talimatlar", "talimat"], ["mcp", "mcp"]];
  const items: CatalogItem[] = [];
  let skipped = 0;
  for (const [key, kind] of groups) {
    const raws = payload[key];
    if (!Array.isArray(raws)) continue;
    for (const raw of raws) {
      try {
        items.push(itemFrom(raw, kind));
      } catch {
        skipped += 1;
      }
    }
  }
  return { items, skipped };
}

/** Diakritiksiz tel değerleri için Türkçe etiket; diğerleri baş harfi büyütülür. */
const SOURCE_LABELS: Record<string, string> = { kullanici: "Kullanıcı", proje: "Proje", komut: "Komut" };

/** "claude+codex" → "Claude · Codex". Köşeli parantezli ham kaynak adı teknik duruyordu. */
function sourceLabels(source: string): string {
  return source.split("+").map((value) => SOURCE_LABELS[value] ?? value.charAt(0).toLocaleUpperCase("tr-TR") + value.slice(1)).join(" · ");
}

/** Alt ajan ayarlarının insan dilindeki adları; bilinmeyen anahtar olduğu gibi yazılır. */
const SETTING_LABELS: Record<string, string> = {
  model: "Model", izin_kipi: "İzin kipi", en_fazla_tur: "En fazla tur", beceriler: "Ön yüklenen beceriler",
  mcp: "MCP sunucuları", bellek: "Kalıcı bellek", efor: "Efor", arka_plan: "Arka plan", yalitim: "Yalıtım",
  kancalar: "Kancalar", yasak_araclar: "Yasak araçlar", baglam: "Bağlam",
};

function settingText(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (typeof value === "boolean") return value ? "evet" : "hayır";
  return String(value);
}

/** Ajan tanımındaki ayarlar (P-034); Claude Code frontmatter alanları Türkçe etiketle. */
function AgentSettings({ ayarlar }: { ayarlar: Record<string, unknown> }) {
  const entries = Object.entries(ayarlar).filter(([, value]) => value !== "" && value !== null && value !== undefined);
  if (entries.length === 0) return null;
  return (
    <dl aria-label="Ajan ayarları" className="skills-catalog__settings">
      {entries.map(([key, value]) => <div key={key}><dt>{SETTING_LABELS[key] ?? key}</dt><dd>{settingText(value)}</dd></div>)}
    </dl>
  );
}

/** `yetenek.detay` ile gelen ajan belleği (P-055). */
interface AgentMemoryInfo {
  kapsam: string;
  dizin: string;
  satir: number;
  konular: string[];
  metin: string;
}

const SCOPE_LABELS: Record<string, string> = { user: "kullanıcı geneli", project: "proje", local: "yerel (git dışı)" };

function memoryFrom(raw: unknown): AgentMemoryInfo | null {
  if (!raw || typeof raw !== "object") return null;
  const info = raw as Record<string, unknown>;
  if (typeof info.kapsam !== "string" || typeof info.dizin !== "string") return null;
  return {
    kapsam: info.kapsam,
    dizin: info.dizin,
    satir: typeof info.satir === "number" ? info.satir : 0,
    konular: Array.isArray(info.konular) ? info.konular.map(String) : [],
    metin: typeof info.metin === "string" ? info.metin : "",
  };
}

/** Ajanın kalıcı belleği: kapsam, dizin, indeks metni ve iki adımlı silme (onay). */
function AgentMemory({ info, onClear }: { info: AgentMemoryInfo; onClear: () => void }) {
  // Silme geri alınamaz (proje kapsamında git'e girmiş dosyalar dahil): tek tık yerine
  // "Evet, sil / Vazgeç" adımı; başka öğe açılınca onay sıfırlanır.
  const [confirming, setConfirming] = useState(false);
  useEffect(() => setConfirming(false), [info.dizin]);
  const empty = !info.metin && info.konular.length === 0;
  return (
    <section aria-label="Ajan belleği" className="skills-catalog__memory">
      <h3>Kalıcı bellek · {SCOPE_LABELS[info.kapsam] ?? info.kapsam}</h3>
      <p>{info.dizin} · {info.satir} satır{info.konular.length > 0 ? ` · konular: ${info.konular.join(", ")}` : ""}</p>
      {info.metin ? <pre>{info.metin}</pre> : <p>Henüz boş; ajan ilk çalışmasında yazar.</p>}
      {confirming ? (
        <div className="skills-catalog__memory-confirm" role="group" aria-label="Silme onayı">
          <span>Bu ajanın belleği ({info.dizin}) tamamen silinecek; geri alınamaz.</span>
          <button onClick={() => { setConfirming(false); onClear(); }} type="button">Evet, sil</button>
          <button onClick={() => setConfirming(false)} type="button">Vazgeç</button>
        </div>
      ) : (
        <button disabled={empty} onClick={() => setConfirming(true)} type="button">Belleği sil</button>
      )}
    </section>
  );
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
  const [memory, setMemory] = useState<AgentMemoryInfo | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState(0);
  // `/skill-doctor` karşılığı: teşhis metni ayrıntı panelinde gösterilir.
  const [diagnosis, setDiagnosis] = useState("");
  // Son açılan öğe kazanır: yavaş gelen eski ayrıntı/bildirim yeni seçimi ezmesin.
  const openRequest = useRef(0);

  useEffect(() => {
    let active = true;
    void client.request("yetenek.katalog", {}).then((payload) => {
      if (!active) return;
      const decoded = decode(payload);
      setItems(decoded.items);
      setSkipped(decoded.skipped);
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
    const requestId = ++openRequest.current;
    setDiagnosis("");
    setSelected(item);
    setDetail("");
    setMemory(null);
    setNotice("");
    void client.request("yetenek.detay", { tur: item.tur, ad: item.kimlik }).then((payload) => {
      if (requestId !== openRequest.current) return;
      if (payload.ok !== true || typeof payload.icerik !== "string") throw new Error(String(payload.metin ?? "Ayrıntı alınamadı."));
      setDetail(payload.icerik);
      setMemory(memoryFrom(payload.bellek));
    }).catch((reason) => { if (requestId === openRequest.current) setError(String(reason)); });
  };

  const toggle = (item: CatalogItem) => {
    const enabled = !item.etkin;
    void client.request("yetenek.etkinlik", { tur: item.tur, ad: item.kimlik, etkin: enabled }).then((payload) => {
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Durum değiştirilemedi."));
      setItems((current) => current.map((entry) => entry.tur === item.tur && entry.kimlik === item.kimlik ? { ...entry, etkin: enabled } : entry));
      setSelected((current) => current?.tur === item.tur && current.kimlik === item.kimlik ? { ...current, etkin: enabled } : current);
    }).catch((reason) => setError(String(reason)));
  };

  const clearMemory = (item: CatalogItem) => {
    const requestId = openRequest.current;
    void client.request("yetenek.bellek_sil", { ad: item.kimlik }).then((payload) => {
      if (requestId !== openRequest.current) return;
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Bellek silinemedi."));
      setMemory((current) => current ? { ...current, satir: 0, konular: [], metin: "" } : current);
      setNotice(`${item.ad} belleği silindi.`);
    }).catch((reason) => { if (requestId === openRequest.current) setNotice(String(reason)); });
  };

  const queueNext = (item: CatalogItem) => {
    const requestId = openRequest.current;
    void client.request("yetenek.kullan", { tur: item.tur, ad: item.kimlik }).then((payload) => {
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Yetenek seçilemedi."));
      // Yanıt gelene dek başka öğe açıldıysa bildirim yeni öğenin paneline karışmasın.
      if (requestId !== openRequest.current) return;
      // `context: fork` beceri: tur ana bağlamı devralan alt ajanda koşar (P-054); kullanıcı görsün.
      setNotice(payload.fork === true
        ? `${item.ad}, sonraki görev için hazır; tur bağlamı devralan alt ajanda koşacak (özet ana sohbete eklenir).`
        : `${item.ad}, sonraki görev için hazır.`);
    }).catch((reason) => setError(String(reason)));
  };

  const reloadCatalog = () => {
    const requestId = ++openRequest.current;
    void client.request("yetenek.yenile", {}).then((payload) => {
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Katalog yenilenemedi."));
      return client.request("yetenek.katalog", {});
    }).then((payload) => {
      if (requestId !== openRequest.current) return;
      const decoded = decode(payload);
      setItems(decoded.items);
      setSkipped(decoded.skipped);
      setSelected(null);
      setNotice(`Katalog yeniden tarandı: ${decoded.items.length} öğe.`);
    }).catch((reason) => setError(String(reason)));
  };

  const diagnoseCatalog = () => {
    const requestId = ++openRequest.current;
    setSelected(null);
    void client.request("yetenek.teshis", {}).then((payload) => {
      if (requestId !== openRequest.current) return;
      if (payload.ok !== true || typeof payload.metin !== "string") throw new Error(String(payload.metin ?? "Teşhis alınamadı."));
      setDiagnosis(payload.metin);
    }).catch((reason) => setError(String(reason)));
  };

  const kart = (item: CatalogItem) => (
    <article className="skills-catalog__card" data-enabled={item.etkin} key={`${item.tur}:${item.kimlik}`} data-selected={selected?.tur === item.tur && selected.kimlik === item.kimlik}>
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
        <div className="skills-catalog__tabs" role="group" aria-label="Katalog işlemleri">
          <button onClick={reloadCatalog} type="button" title="Diskten yeniden tara (/skills reload)">Yenile</button>
          <button onClick={diagnoseCatalog} type="button" title="Eksik açıklama, kopya ad, uzun gövde (/skill-doctor)">Teşhis</button>
        </div>
      </div>
      {error && <p className="skills-catalog__error" role="alert">{error}</p>}
      {skipped > 0 && <p className="skills-catalog__error" role="status">{skipped} katalog öğesi bozuk olduğu için atlandı.</p>}
      <div className="skills-catalog__layout">
        <section aria-label="Yetenek kataloğu" className="skills-catalog__list">
          {filtered.length === 0 && <p className="skills-catalog__empty">Eşleşen öğe yok.</p>}
          {etkinler.length > 0 && <h3 className="skills-catalog__group">Etkin · {etkinler.length}</h3>}
          {etkinler.length > 0 && <div className="skills-catalog__grid">{etkinler.map(kart)}</div>}
          {digerleri.length > 0 && <h3 className="skills-catalog__group">{etkinler.length > 0 ? "Diğerleri" : "Tümü"}</h3>}
          {digerleri.length > 0 && <div className="skills-catalog__grid">{digerleri.map(kart)}</div>}
        </section>
        <aside aria-label="Yetenek ayrıntısı" className="skills-catalog__detail">
          {!selected && diagnosis && <pre aria-label="Beceri teşhisi">{diagnosis}</pre>}
          {selected ? <><div className="skills-catalog__detail-head"><SkillAvatar item={selected} /><div><h2>{selected.ad}</h2><span>{kindLabels[selected.tur]} · {sourceLabels(selected.kaynak)}{selected.izinler.length > 0 ? ` · ${selected.izinler.join(", ")}` : ""}</span></div></div><AgentSettings ayarlar={selected.ayarlar} /><pre>{detail || "Yükleniyor…"}</pre>{memory && <AgentMemory info={memory} onClear={() => clearMemory(selected)} />}{selected.tur !== "talimat" && <button disabled={!selected.etkin} onClick={() => queueNext(selected)} type="button">Bu {selected.tur === "beceri" ? "beceriyi" : selected.tur === "ajan" ? "ajanı" : "MCP'yi"} sonraki turda kullan</button>}{notice && <p aria-live="polite">{notice}</p>}</> : !diagnosis && <p>Ne yaptığını, nereden geldiğini ve hangi izinleri kullandığını görmek için bir beceri seç.</p>}
        </aside>
      </div>
    </main>
  );
}
