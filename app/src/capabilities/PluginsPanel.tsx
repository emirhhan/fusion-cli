import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import "./PluginsPanel.css";

/**
 * Eklentiler (P-059) — Claude Code `/plugin` ekranının karşılığı: Kurulu · Keşfet · Pazarlar.
 *
 * Bir eklenti beceri, komut, ajan, çıktı stili, kanca ve MCP sunucusunu tek paket olarak getirir.
 * Kanca/MCP Fusion dışında komut çalıştırdığı için kurulum iki adımdır: önce önizleme (bileşenler,
 * MCP komutları, uyarılar) gösterilir, kullanıcı "Onaylıyorum, kur" deyince `onay: true` gider.
 * Dosyaları kurulumdan sonra değişen eklenti "değişmiş" görünür ve yeniden onaylanana dek yüklenmez;
 * "Yeniden onayla" önce güncel içeriğin önizlemesini ister, onay o önizlemenin karmasıyla gider.
 * Önizleme karması (`karma`) onaylı isteğe `beklenen_karma` olarak eklenir: kullanıcı kartı okurken
 * kaynak değiştiyse sunucu kurmaz.
 */

interface Components { beceri: number; komut: number; ajan: number; stil: number; kanca: boolean; mcp: boolean }
interface InstalledPlugin {
  ad: string; surum: string; aciklama: string; durum: string; ayrinti: string;
  kaynak: string; pazar: string; etkin: boolean; calistirilabilir: boolean; bilesenler: Components;
}
interface Preview {
  ad: string; surum: string; aciklama: string; yazar: string; bilesenler: Components;
  kanca_sayisi: number; kancalar: string[]; kancalar_calismaz: boolean; mcp: { ad: string; hedef: string }[];
  calistirilabilir: boolean; baglam_maliyeti: number; uyarilar: string[]; hatalar: string[]; karma: string;
}
/** Ekrandaki önizleme: yeni kurulum mu, değişmiş eklentinin yeniden onayı mı. */
type PendingPreview =
  | { mode: "kur"; kaynak: string; data: Preview }
  | { mode: "guven" | "guncelle"; ad: string; data: Preview };
interface CatalogEntry { ad: string; pazar: string; surum: string; aciklama: string; kurulu: boolean }
interface Marketplace { ad: string; kaynak: string; tur: string }

const EMPTY_COMPONENTS: Components = { beceri: 0, komut: 0, ajan: 0, stil: 0, kanca: false, mcp: false };

function components(raw: unknown): Components {
  if (!raw || typeof raw !== "object") return EMPTY_COMPONENTS;
  const item = raw as Record<string, unknown>;
  const count = (key: string) => (typeof item[key] === "number" ? (item[key] as number) : 0);
  return { beceri: count("beceri"), komut: count("komut"), ajan: count("ajan"), stil: count("stil"), kanca: item.kanca === true, mcp: item.mcp === true };
}

function texts(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((value): value is string => typeof value === "string") : [];
}

function str(raw: unknown): string {
  return typeof raw === "string" ? raw : "";
}

function installedFrom(raw: unknown): InstalledPlugin | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.ad !== "string") return null;
  return {
    ad: item.ad, surum: str(item.surum), aciklama: str(item.aciklama), durum: str(item.durum), ayrinti: str(item.ayrinti),
    kaynak: str(item.kaynak), pazar: str(item.pazar), etkin: item.etkin === true, calistirilabilir: item.calistirilabilir === true,
    bilesenler: components(item.bilesenler),
  };
}

function previewFrom(raw: unknown): Preview | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  const servers = Array.isArray(item.mcp) ? item.mcp.filter((s): s is { ad: string; hedef: string } => !!s && typeof s === "object" && typeof (s as Record<string, unknown>).ad === "string") : [];
  return {
    ad: str(item.ad), surum: str(item.surum), aciklama: str(item.aciklama), yazar: str(item.yazar), bilesenler: components(item.bilesenler),
    kanca_sayisi: typeof item.kanca_sayisi === "number" ? item.kanca_sayisi : 0, kancalar: texts(item.kancalar),
    kancalar_calismaz: item.kancalar_calismaz === true, mcp: servers.map((s) => ({ ad: s.ad, hedef: str(s.hedef) })),
    calistirilabilir: item.calistirilabilir === true, baglam_maliyeti: typeof item.baglam_maliyeti === "number" ? item.baglam_maliyeti : 0,
    uyarilar: texts(item.uyarilar), hatalar: texts(item.hatalar), karma: str(item.karma),
  };
}

/** "2 beceri · 1 komut · kanca · MCP" */
export function componentSummary(value: Components): string {
  const parts = [
    value.beceri ? `${value.beceri} beceri` : "", value.komut ? `${value.komut} komut` : "",
    value.ajan ? `${value.ajan} ajan` : "", value.stil ? `${value.stil} çıktı stili` : "",
    value.kanca ? "kanca" : "", value.mcp ? "MCP" : "",
  ].filter(Boolean);
  return parts.join(" · ") || "bileşen yok";
}

const STATUS_TONE: Record<string, string> = { etkin: "on", kapalı: "off", değişmiş: "warn", bozuk: "warn" };

type Tab = "kurulu" | "kesfet" | "pazarlar";

interface PreviewCardProps { preview: Preview; mode: PendingPreview["mode"]; onConfirm: () => void; onCancel: () => void; busy: boolean }

const CONFIRM_LABEL: Record<PendingPreview["mode"], string> = { kur: "Onaylıyorum, kur", guven: "Onaylıyorum", guncelle: "Onaylıyorum, güncelle" };

function PreviewCard({ preview, mode, onConfirm, onCancel, busy }: PreviewCardProps) {
  const blocked = preview.hatalar.length > 0;
  const reapprove = mode === "guven";
  const confirmLabel = mode === "kur" && !preview.calistirilabilir ? "Kur" : CONFIRM_LABEL[mode];
  return (
    <section aria-label="Eklenti önizlemesi" className="plugins-panel__preview">
      <h3>{preview.ad} {preview.surum}</h3>
      {preview.aciklama && <p>{preview.aciklama}</p>}
      <p className="plugins-panel__meta">{componentSummary(preview.bilesenler)} · bağlam ~{preview.baglam_maliyeti} token/tur{preview.yazar ? ` · ${preview.yazar}` : ""}</p>
      {reapprove && <p className="plugins-panel__warn" role="note">Dosyalar kurulumdan sonra değişti. Aşağıdaki güncel içerik onaylanınca yeniden yüklenir.</p>}
      {preview.kancalar.length > 0 && <ul aria-label="Kanca komutları">{preview.kancalar.map((line) => <li key={line}><code>{line}</code></li>)}</ul>}
      {preview.kancalar_calismaz && <p className="plugins-panel__meta">Not: Fusion bu sürümde eklenti kancalarını henüz çalıştırmıyor; kancalar onaylansa da tetiklenmez.</p>}
      {preview.mcp.length > 0 && <ul aria-label="MCP sunucuları">{preview.mcp.map((server) => <li key={server.ad}><code>{server.ad}</code> → <code>{server.hedef}</code></li>)}</ul>}
      {preview.uyarilar.map((warning) => <p className="plugins-panel__warn" key={warning}>{warning}</p>)}
      {preview.hatalar.map((problem) => <p className="plugins-panel__error" key={problem} role="alert">{problem}</p>)}
      {preview.calistirilabilir && (
        <p className="plugins-panel__warn" role="note">
          Bu eklenti Fusion dışında komut çalıştırabilir ({[preview.kanca_sayisi ? `${preview.kanca_sayisi} kanca` : "", preview.mcp.length ? `${preview.mcp.length} MCP sunucusu` : ""].filter(Boolean).join(", ")}). Kaynağına güveniyorsan kur; MCP araç çağrıları yine onay ister.
        </p>
      )}
      <div className="plugins-panel__actions">
        <button className="plugins-panel__primary" disabled={busy || blocked} onClick={onConfirm} type="button">{confirmLabel}</button>
        <button disabled={busy} onClick={onCancel} type="button">Vazgeç</button>
      </div>
    </section>
  );
}

export function PluginsPanel({ client, onChanged }: { client: ProtocolClient; onChanged?: () => void }) {
  const [tab, setTab] = useState<Tab>("kurulu");
  const [plugins, setPlugins] = useState<InstalledPlugin[]>([]);
  const [markets, setMarkets] = useState<Marketplace[]>([]);
  const [allDisabled, setAllDisabled] = useState(false);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [source, setSource] = useState("");
  const [marketSource, setMarketSource] = useState("");
  const [preview, setPreview] = useState<PendingPreview | null>(null);
  const [confirmRemove, setConfirmRemove] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const applyList = useCallback((payload: Record<string, unknown>) => {
    if (payload.ok !== true) throw new Error(str(payload.metin) || "Eklentiler alınamadı.");
    setPlugins((Array.isArray(payload.eklentiler) ? payload.eklentiler : []).map(installedFrom).filter((item): item is InstalledPlugin => item !== null));
    setMarkets((Array.isArray(payload.pazarlar) ? payload.pazarlar : []).filter((m): m is Marketplace => !!m && typeof m === "object" && typeof (m as Record<string, unknown>).ad === "string").map((m) => ({ ad: m.ad, kaynak: str(m.kaynak), tur: str(m.tur) })));
    setAllDisabled(payload.hepsi_kapali === true);
  }, []);

  const load = useCallback(async () => {
    try { applyList(await client.request("eklenti.listele", {})); setError(null); } catch (reason) { setError(errorMessage(reason)); }
  }, [applyList, client]);
  useEffect(() => { void load(); }, [load]);

  const run = async (name: string, data: Record<string, unknown>, done: string) => {
    setBusy(true); setNotice(""); setError(null);
    try {
      const payload = await client.request(name, data);
      if (payload.ok !== true) throw new Error(str(payload.metin) || "İşlem yapılamadı.");
      if (Array.isArray(payload.eklentiler) && name !== "eklenti.kesfet") applyList(payload); else await load();
      setNotice(done);
      if (payload.yenile === true) onChanged?.();
      return payload;
    } catch (reason) { setError(errorMessage(reason)); return null; } finally { setBusy(false); }
  };

  const askPreview = async (kaynak: string) => {
    if (!kaynak.trim()) return;
    setBusy(true); setError(null); setNotice(""); setPreview(null);
    try {
      const payload = await client.request("eklenti.onizle", { kaynak: kaynak.trim() });
      const data = previewFrom(payload.onizleme);
      if (payload.ok !== true || !data) throw new Error(str(payload.metin) || "Önizleme alınamadı.");
      setPreview({ mode: "kur", kaynak: kaynak.trim(), data });
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  };

  /** Değişmiş eklenti: önce güncel içeriğin önizlemesi (onaysız `eklenti.guven`), sonra onay. */
  const askReapproval = async (ad: string) => {
    setBusy(true); setError(null); setNotice(""); setPreview(null);
    try {
      const payload = await client.request("eklenti.guven", { ad });
      const data = previewFrom(payload.onizleme);
      if (payload.onay_gerekli !== true || !data) throw new Error(str(payload.metin) || "Önizleme alınamadı.");
      setPreview({ mode: "guven", ad, data });
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  };

  /** Güncelle: içerik aynıysa "zaten güncel"; kanca/MCP içeren yeni içerik önce önizlenir. */
  const askUpdate = async (ad: string) => {
    setBusy(true); setError(null); setNotice(""); setPreview(null);
    try {
      const payload = await client.request("eklenti.guncelle", { ad });
      const data = previewFrom(payload.onizleme);
      if (payload.onay_gerekli === true && data) { setPreview({ mode: "guncelle", ad, data }); return; }
      if (payload.ok !== true) throw new Error(str(payload.metin) || "Güncellenemedi.");
      applyList(payload);
      setNotice(payload.guncel === true ? `${ad} zaten güncel.` : `${ad} güncellendi.`);
      if (payload.yenile === true) onChanged?.();
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  };

  const validate = async (ad: string) => {
    setBusy(true); setError(null); setNotice("");
    try {
      const payload = await client.request("eklenti.dogrula", { ad });
      if (payload.ok !== true) throw new Error(str(payload.metin) || "Doğrulanamadı.");
      const problems = [...texts(payload.hatalar), ...texts(payload.uyarilar)];
      const head = payload.gecerli === true ? `${ad} geçerli` : `${ad} geçersiz`;
      setNotice(`${head} · bütünlük: ${str(payload.butunluk)}${problems.length ? ` · ${problems.join(" · ")}` : ""}`);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  };

  const confirmPreview = async () => {
    if (!preview) return;
    const beklenen_karma = preview.data.karma;
    // Önizleme kullanıcıya gösterildi: onay bu tıklamadır ve yalnız gösterilen içerik için geçerli.
    let done: Record<string, unknown> | null;
    if (preview.mode === "kur") done = await run("eklenti.kur", { kaynak: preview.kaynak, onay: preview.data.calistirilabilir, beklenen_karma }, `${preview.data.ad} kuruldu.`);
    else if (preview.mode === "guven") done = await run("eklenti.guven", { ad: preview.ad, onay: true, beklenen_karma }, `${preview.ad} yeniden onaylandı.`);
    else done = await run("eklenti.guncelle", { ad: preview.ad, onay: true, beklenen_karma }, `${preview.ad} güncellendi.`);
    if (done) { setPreview(null); if (preview.mode === "kur") setSource(""); }
  };

  const card = preview && <PreviewCard busy={busy} mode={preview.mode} onCancel={() => setPreview(null)} onConfirm={() => void confirmPreview()} preview={preview.data} />;

  const discover = async () => {
    setTab("kesfet"); setBusy(true); setError(null);
    try {
      const payload = await client.request("eklenti.kesfet", {});
      if (payload.ok !== true) throw new Error(str(payload.metin) || "Pazarlar okunamadı.");
      setCatalog((Array.isArray(payload.eklentiler) ? payload.eklentiler : []).filter((e): e is CatalogEntry => !!e && typeof e === "object" && typeof (e as Record<string, unknown>).ad === "string").map((e) => ({ ad: e.ad, pazar: str(e.pazar), surum: str(e.surum), aciklama: str(e.aciklama), kurulu: e.kurulu === true })));
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  };

  return (
    <section aria-label="Eklentiler" className="plugins-panel">
      <div aria-label="Eklenti görünümü" className="skills-catalog__tabs" role="tablist">
        <button aria-selected={tab === "kurulu"} onClick={() => setTab("kurulu")} role="tab" type="button">Kurulu · {plugins.length}</button>
        <button aria-selected={tab === "kesfet"} onClick={() => void discover()} role="tab" type="button">Keşfet</button>
        <button aria-selected={tab === "pazarlar"} onClick={() => setTab("pazarlar")} role="tab" type="button">Pazarlar · {markets.length}</button>
      </div>
      {error && <p className="plugins-panel__error" role="alert">{error}</p>}
      {notice && <p aria-live="polite" className="plugins-panel__meta">{notice}</p>}
      {tab === "kurulu" && (
        <>
          <form className="plugins-panel__form" onSubmit={(event) => { event.preventDefault(); void askPreview(source); }}>
            <input aria-label="Eklenti kaynağı" onChange={(event) => setSource(event.target.value)} placeholder="Klasör, https://github.com/sahip/repo, sahip/repo ya da ad@pazar" value={source} />
            <button disabled={busy || !source.trim()} type="submit">Önizle</button>
          </form>
          {card}
          <label className="plugins-panel__global">
            <input aria-label="Bütün eklentiler" checked={!allDisabled} disabled={busy} onChange={(event) => void run("eklenti.etkinlik", { hepsi: true, etkin: event.target.checked }, event.target.checked ? "Eklentiler açıldı." : "Bütün eklentiler kapatıldı.")} type="checkbox" />
            <span>Bütün eklentiler {allDisabled ? "kapalı" : "açık"}</span>
          </label>
          {plugins.length === 0 && <p className="skills-catalog__empty">Kurulu eklenti yok. Bir kaynak gir ya da Pazarlar'dan ekle (terminalde <code>/plugin</code>).</p>}
          <ul aria-label="Kurulu eklentiler" className="plugins-panel__list">
            {plugins.map((plugin) => (
              <li className="plugins-panel__item" data-status={STATUS_TONE[plugin.durum] ?? "off"} key={plugin.ad}>
                <div className="plugins-panel__text">
                  <strong>{plugin.ad}{plugin.surum ? ` ${plugin.surum}` : ""}</strong>
                  {plugin.aciklama && <span>{plugin.aciklama}</span>}
                  <small>{plugin.durum} · {componentSummary(plugin.bilesenler)} · {plugin.pazar || plugin.kaynak}</small>
                  {plugin.ayrinti && <small className="plugins-panel__warn">{plugin.ayrinti}</small>}
                </div>
                <div className="plugins-panel__actions">
                  {plugin.durum === "değişmiş" && <button disabled={busy} onClick={() => void askReapproval(plugin.ad)} type="button">İncele ve yeniden onayla</button>}
                  <button aria-label={`${plugin.ad} güncelle`} disabled={busy} onClick={() => void askUpdate(plugin.ad)} type="button">Güncelle</button>
                  <button aria-label={`${plugin.ad} doğrula`} disabled={busy} onClick={() => void validate(plugin.ad)} type="button">Doğrula</button>
                  <button aria-checked={plugin.etkin} aria-label={`${plugin.ad} etkin`} className="skills-catalog__switch" disabled={busy} onClick={() => void run("eklenti.etkinlik", { ad: plugin.ad, etkin: !plugin.etkin }, `${plugin.ad} ${plugin.etkin ? "kapatıldı" : "açıldı"}.`)} role="switch" type="button"><span /></button>
                  {confirmRemove === plugin.ad ? (
                    <>
                      <button disabled={busy} onClick={() => { setConfirmRemove(""); void run("eklenti.kaldir", { ad: plugin.ad }, `${plugin.ad} kaldırıldı (çöpte).`); }} type="button">Evet, kaldır</button>
                      <button onClick={() => setConfirmRemove("")} type="button">Vazgeç</button>
                    </>
                  ) : <button disabled={busy} onClick={() => setConfirmRemove(plugin.ad)} type="button">Kaldır</button>}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {tab === "kesfet" && (
        <>
          {card}
          {catalog.length === 0 && <p className="skills-catalog__empty">Pazarlarda eklenti yok. Önce Pazarlar sekmesinden bir pazar ekle.</p>}
          <ul aria-label="Pazardaki eklentiler" className="plugins-panel__list">
            {catalog.map((entry) => (
              <li className="plugins-panel__item" key={`${entry.pazar}:${entry.ad}`}>
                <div className="plugins-panel__text">
                  <strong>{entry.ad}{entry.surum ? ` ${entry.surum}` : ""}</strong>
                  {entry.aciklama && <span>{entry.aciklama}</span>}
                  <small>{entry.pazar}{entry.kurulu ? " · kurulu" : ""}</small>
                </div>
                <button disabled={busy || entry.kurulu} onClick={() => void askPreview(`${entry.ad}@${entry.pazar}`)} type="button">{entry.kurulu ? "Kurulu" : "İncele ve kur"}</button>
              </li>
            ))}
          </ul>
        </>
      )}
      {tab === "pazarlar" && (
        <>
          <form className="plugins-panel__form" onSubmit={(event) => { event.preventDefault(); void run("eklenti.pazar_ekle", { kaynak: marketSource.trim() }, "Pazar eklendi.").then((ok) => ok && setMarketSource("")); }}>
            <input aria-label="Pazar kaynağı" onChange={(event) => setMarketSource(event.target.value)} placeholder="Klasör, sahip/repo, https adresi ya da 'resmi'" value={marketSource} />
            <button disabled={busy || !marketSource.trim()} type="submit">Pazar ekle</button>
          </form>
          {markets.length === 0 && <p className="skills-catalog__empty">Kayıtlı pazar yok. <code>resmi</code> yazarak Claude Code'un resmi pazarını ekleyebilirsin.</p>}
          <ul aria-label="Pazar yerleri" className="plugins-panel__list">
            {markets.map((market) => (
              <li className="plugins-panel__item" key={market.ad}>
                <div className="plugins-panel__text"><strong>{market.ad}</strong><small>{market.tur} · {market.kaynak}</small></div>
                <div className="plugins-panel__actions">
                  <button aria-label={`${market.ad} pazarını güncelle`} disabled={busy} onClick={() => void run("eklenti.pazar_guncelle", { ad: market.ad }, `${market.ad} pazarı güncellendi.`)} type="button">Güncelle</button>
                  <button disabled={busy} onClick={() => void run("eklenti.pazar_kaldir", { ad: market.ad }, `${market.ad} pazarı kaldırıldı.`)} type="button">Kaldır</button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
