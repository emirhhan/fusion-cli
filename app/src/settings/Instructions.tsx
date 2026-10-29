import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

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

  const load = useCallback(async () => {
    try {
      const veri = (await client.request("ayar.talimat", {})) as {
        ok?: boolean;
        metin?: string;
        sinir?: number;
      };
      if (!veri?.ok) {
        setNotice(veri?.metin ?? "Talimat okunamadı.");
        return;
      }
      setText(veri.metin ?? "");
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
    </article>
  );
}
