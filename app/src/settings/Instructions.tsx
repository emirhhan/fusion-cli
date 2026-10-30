import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

/** `ayar.talimat` ile gelen, tur başında bağlama giren talimat dosyası. */
export interface InstructionLayer {
  kaynak: string;
  katman: string;
  karakter: number;
  kirpilan: number;
  guvenilir: boolean;
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
export function Instructions({ client }: { client: ProtocolClient }) {
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

  const load = useCallback(async () => {
    try {
      const veri = (await client.request("ayar.talimat", {})) as {
        ok?: boolean;
        metin?: string;
        sinir?: number;
        katmanlar?: unknown;
        notlar?: unknown;
      };
      if (!veri?.ok) {
        setNotice(veri?.metin ?? "Talimat okunamadı.");
        return;
      }
      setText(veri.metin ?? "");
      setLayers(decodeLayers(veri.katmanlar));
      setLayerNotes(Array.isArray(veri.notlar) ? veri.notlar.filter((n): n is string => typeof n === "string") : []);
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
      <h4>Tur başında yüklenen talimat dosyaları</h4>
      {layers.length === 0 ? (
        <p className="settings__hint">
          Bu klasörde CLAUDE.md / AGENTS.md ya da ~/.claude/CLAUDE.md bulunmadı. Sohbette <code>/init</code> ile oluşturabilirsin.
        </p>
      ) : (
        <ul aria-label="Yüklenen talimat katmanları" className="settings__list">
          {layers.map((layer) => (
            <li key={`${layer.katman}:${layer.kaynak}`}>
              <strong>{layer.kaynak}</strong>
              <code>
                {LAYER_LABELS[layer.katman] ?? layer.katman} · {layer.karakter} karakter
                {layer.kirpilan > 0 ? ` · ${layer.kirpilan} kırpıldı` : ""}
                {layer.guvenilir ? "" : " · depo içeriği"}
              </code>
            </li>
          ))}
        </ul>
      )}
      {layerNotes.map((note) => <p className="settings__hint" key={note} role="note">{note}</p>)}
    </article>
  );
}
