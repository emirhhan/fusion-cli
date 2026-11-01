import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./Instructions.css";

/** `ayar.talimat` ile gelen, tur başında bağlama giren talimat dosyası. */
export interface InstructionLayer {
  kaynak: string;
  katman: string;
  karakter: number;
  kirpilan: number;
  guvenilir: boolean;
  /** `.claude/rules` kuralı için `paths:` desenleri; boşsa kural her yerde geçerli. */
  kapsam: string[];
}

const LAYER_LABELS: Record<string, string> = {
  kullanici: "Kullanıcı",
  proje: "Proje",
  import: "@import",
  baglanti: "Bağlantı",
  kural: "Kural",
};

function decodeLayers(raw: unknown): InstructionLayer[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    if (typeof row.kaynak !== "string") return [];
    return [{
      kaynak: row.kaynak,
      katman: typeof row.katman === "string" ? row.katman : "proje",
      karakter: typeof row.karakter === "number" ? row.karakter : 0,
      kirpilan: typeof row.kirpilan === "number" ? row.kirpilan : 0,
      guvenilir: row.guvenilir === true,
      kapsam: Array.isArray(row.kapsam) ? row.kapsam.filter((p): p is string => typeof p === "string") : [],
    }];
  });
}

/**
 * Kalıcı talimat düzenleyici.
 *
 * Sistem istemi burada DÜZENLENMEZ: Fusion'ın kimliği ve onay sözleşmesi
 * orada durur ve kullanıcıya açılırsa ürün kendi kurallarından edilebilir.
 * Buraya yazılan metin ek bir blok olarak her tura girer.
 */
export function Instructions({ client, onRunCommand }: { client: ProtocolClient; onRunCommand?: (command: string) => void }) {
  const [text, setText] = useState("");
  const [limit, setLimit] = useState(4000);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  // Ölçüldü (29 Ekim, U2-36): okuma başarısızken metin boş kalıyordu ve Kaydet, mevcut
  // talimatın üzerine boş/yeni metni yazabiliyordu. Yüklenmeden düzenleme/kaydetme kapalı.
  const [loaded, setLoaded] = useState(false);
  // Tur başında bağlama giren talimat katmanları (~/.claude/CLAUDE.md, CLAUDE.md, kurallar…).
  const [layers, setLayers] = useState<InstructionLayer[]>([]);
  const [layerNotes, setLayerNotes] = useState<string[]>([]);
  // `/doctor prompt` önerileri (P-021): kırpma, şüpheli satır, eksik doğrulama bölümü.
  const [suggestions, setSuggestions] = useState<string[]>([]);
  // Claude Code (#145): kararı verilmemiş dış `@import` hedefleri; onay ya da ret istenir.
  const [externalImports, setExternalImports] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const veri = (await client.request("ayar.talimat", {})) as {
        ok?: boolean;
        metin?: string;
        sinir?: number;
        katmanlar?: unknown;
        notlar?: unknown;
        oneriler?: unknown;
        dis_importlar?: unknown;
      };
      if (!veri?.ok) {
        setNotice(veri?.metin ?? "Talimat okunamadı.");
        return;
      }
      setText(veri.metin ?? "");
      setLayers(decodeLayers(veri.katmanlar));
      setLayerNotes(Array.isArray(veri.notlar) ? veri.notlar.filter((n): n is string => typeof n === "string") : []);
      setSuggestions(Array.isArray(veri.oneriler) ? veri.oneriler.filter((n): n is string => typeof n === "string") : []);
      setExternalImports(
        Array.isArray(veri.dis_importlar) ? veri.dis_importlar.filter((n): n is string => typeof n === "string") : [],
      );
      if (typeof veri.sinir === "number") setLimit(veri.sinir);
      setDirty(false);
      setLoaded(true);
      setNotice(null);
    } catch {
      setNotice("Talimat okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  const decideImports = async (onay: boolean) => {
    try {
      const sonuc = (await client.request("ayar.dis_import_karari", { onay })) as { ok?: boolean; metin?: string };
      setNotice(sonuc?.metin ?? null);
      if (sonuc?.ok) await load();
    } catch {
      setNotice("Dış import kararı kaydedilemedi.");
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const sonuc = (await client.request("ayar.talimat_kaydet", { metin: text })) as {
        ok?: boolean;
        metin?: string;
      };
      if (!sonuc?.ok) {
        setNotice(sonuc?.metin ?? "Talimat kaydedilemedi.");
        return;
      }
      setDirty(false);
      setNotice("Talimat kaydedildi.");
    } catch {
      setNotice("Talimat kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="settings__card settings__card--wide">
      <h3>Kalıcı talimat</h3>
      <p className="settings__hint">
        Her sohbette geçerli olacak tercihlerin. Onay ve araç kuralları
        değişmez; bu metin onların yerine geçmez.
      </p>
      <label className="settings__sr-only" htmlFor="settings-instructions">
        Kalıcı talimat
      </label>
      <textarea
        id="settings-instructions"
        maxLength={limit}
        onChange={(event) => {
          setText(event.target.value);
          setDirty(true);
          setNotice(null);
        }}
        disabled={!loaded}
        placeholder="Örnek: Cevapları kısa tut, kod örneklerinde yorumları Türkçe yaz."
        rows={5}
        value={text}
      />
      <div className="settings__actions">
        <button disabled={busy || !dirty || !loaded} onClick={() => void save()} type="button">
          Kaydet
        </button>
        {!loaded && (
          <button onClick={() => void load()} type="button">
            Yeniden oku
          </button>
        )}
        <small>
          {text.length}/{limit}
        </small>
      </div>
      {notice && <p className="settings__hint" role="status">{notice}</p>}
      {layers.length === 0 ? (
        <>
          <h4 className="instructions__layers-title">Tur başında yüklenen talimat dosyaları</h4>
          <p className="settings__hint">
            Bu klasörde CLAUDE.md / AGENTS.md ya da ~/.claude/CLAUDE.md bulunmadı. Sohbette <code>/init</code> ile oluşturabilirsin.
          </p>
        </>
      ) : (
        // Kural dosyaları çoğalınca liste ekranı boyluyordu: varsayılan kapalı, başlıkta sayı;
        // açılınca kendi içinde kayar ve uzun yollar satırı taşırmadan kırılır.
        <details className="instructions__layers">
          <summary>Tur başında yüklenen talimat dosyaları ({layers.length})</summary>
          <ul aria-label="Yüklenen talimat katmanları" className="instructions__layer-list">
            {layers.map((layer) => (
              <li key={`${layer.katman}:${layer.kaynak}`}>
                <strong title={layer.kaynak}>{layer.kaynak}</strong>
                <small>
                  {LAYER_LABELS[layer.katman] ?? layer.katman} · {layer.karakter} karakter
                  {layer.kirpilan > 0 ? ` · ${layer.kirpilan} kırpıldı` : ""}
                  {layer.katman === "kural" ? ` · ${layer.kapsam.length > 0 ? layer.kapsam.join(", ") : "her yerde"}` : ""}
                  {layer.guvenilir ? "" : " · depo içeriği"}
                </small>
              </li>
            ))}
          </ul>
        </details>
      )}
      {externalImports.length > 0 && (
        <section aria-label="Dış import onayı" className="settings__card" role="alertdialog">
          <p className="settings__hint">
            Bu projenin talimat dosyaları çalışma dizini dışındaki dosyaları içe aktarıyor. İzin verilsin mi?
            Reddedersen kapalı kalır ve bir daha sorulmaz.
          </p>
          <ul className="instructions__layer-list">
            {externalImports.map((item) => <li key={item}><code>{item}</code></li>)}
          </ul>
          <div className="settings__actions">
            <button onClick={() => void decideImports(true)} type="button">İzin ver</button>
            <button onClick={() => void decideImports(false)} type="button">Reddet (bir daha sorma)</button>
          </div>
        </section>
      )}
      {layerNotes.map((note) => <p className="settings__hint" key={note} role="note">{note}</p>)}
      {suggestions.length > 0 && (
        <ul aria-label="Talimat önerileri" className="settings__list">
          {suggestions.map((item) => <li key={item}><strong>→ {item}</strong></li>)}
        </ul>
      )}
      {onRunCommand && (
        <div className="settings__actions">
          <button onClick={() => onRunCommand("/init")} type="button">Talimat oluştur (/init)</button>
          <button onClick={() => onRunCommand("/doctor prompt")} type="button">Talimatı denetle</button>
        </div>
      )}
    </article>
  );
}
