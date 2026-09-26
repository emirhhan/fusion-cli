import { useEffect, useRef, useState } from "react";
import { assetUrl } from "../platform/assetUrl";
import "./ImageCreate.css";

interface ImageClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

interface Secenek {
  deger: string;
  etiket: string;
}

export interface UretilenGorsel {
  yol: string;
  genislik: number;
  yukseklik: number;
  istem: string;
  saglayici: string;
}

export interface ImageCreateProps {
  client: ImageClient | null;
  /** Test ve önizleme için: yerel yolu gösterilebilir adrese çevirir. */
  toUrl?: (path: string) => string | null;
  reveal?: (path: string) => Promise<void>;
}

const ORNEKLER = [
  "Beyaz stüdyo arka planında kırmızı motosiklet kaskı, ürün fotoğrafı",
  "Yağmurlu İstanbul sokağında gece sürüşü yapan motosikletli, sinematik",
  "Siyah deri motosiklet eldiveni, ahşap masa, doğal ışık",
];

async function revealWithSystem(path: string): Promise<void> {
  const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
  await revealItemInDir(path);
}

/**
 * Görsel oluştur — bağlı Gemini/ChatGPT web oturumu görseli üretir, dosya
 * `~/Pictures/Fusion` altına kaydedilir. Sonuçlar bu sayfada en yeni üstte listelenir.
 */
export function ImageCreate({ client, toUrl = assetUrl, reveal = revealWithSystem }: ImageCreateProps) {
  const [istem, setIstem] = useState("");
  const [secenekler, setSecenekler] = useState<Secenek[]>([]);
  const [saglayici, setSaglayici] = useState("");
  const [calisiyor, setCalisiyor] = useState(false);
  const [gecen, setGecen] = useState(0);
  const [hata, setHata] = useState<string | null>(null);
  const [gorseller, setGorseller] = useState<UretilenGorsel[]>([]);
  const kutuRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!client) return;
    let iptal = false;
    void client.request("gorsel.saglayicilar", {}).then((sonuc) => {
      if (iptal) return;
      const liste = Array.isArray(sonuc.secenekler) ? (sonuc.secenekler as Secenek[]) : [];
      setSecenekler(liste);
      setSaglayici((mevcut) => mevcut || liste[0]?.deger || "");
    }).catch(() => undefined);
    kutuRef.current?.focus();
    return () => { iptal = true; };
  }, [client]);

  useEffect(() => {
    if (!calisiyor) return;
    const baslangic = Date.now();
    const sayac = window.setInterval(() => setGecen(Math.round((Date.now() - baslangic) / 1000)), 1000);
    return () => window.clearInterval(sayac);
  }, [calisiyor]);

  const olustur = async () => {
    const metin = istem.trim();
    if (!client || !metin || calisiyor) return;
    setCalisiyor(true);
    setGecen(0);
    setHata(null);
    try {
      const sonuc = await client.request("gorsel.olustur", { istem: metin, saglayici });
      if (sonuc.ok !== true) {
        setHata(String(sonuc.metin ?? "Görsel üretilemedi."));
        return;
      }
      const dosyalar = Array.isArray(sonuc.dosyalar) ? sonuc.dosyalar as Record<string, unknown>[] : [];
      const yeni = dosyalar.map((dosya) => ({
        yol: String(dosya.yol),
        genislik: Number(dosya.genislik ?? 0),
        yukseklik: Number(dosya.yukseklik ?? 0),
        istem: metin,
        saglayici: String(sonuc.saglayici ?? ""),
      }));
      setGorseller((onceki) => [...yeni, ...onceki]);
    } catch (reason) {
      setHata(`Görsel üretilemedi: ${String(reason)}`);
    } finally {
      setCalisiyor(false);
    }
  };

  return (
    <section aria-label="Görsel oluştur" className="image-create">
      {/* Başlık uygulamanın üst çubuğunda; burada tekrar yazılmaz. */}
      <header className="image-create__head">
        <p>Bağlı Gemini ya da ChatGPT hesabın görseli üretir; dosyalar Resimler › Fusion klasörüne kaydedilir.</p>
      </header>

      <form className="image-create__composer" onSubmit={(event) => { event.preventDefault(); void olustur(); }}>
        <textarea
          aria-label="Görsel istemi"
          disabled={calisiyor}
          onChange={(event) => setIstem(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void olustur(); }
          }}
          placeholder="Ne görmek istediğini anlat…"
          ref={kutuRef}
          rows={3}
          value={istem}
        />
        <div className="image-create__bar">
          {secenekler.length > 1 ? (
            <select aria-label="Sağlayıcı" disabled={calisiyor} onChange={(event) => setSaglayici(event.target.value)} value={saglayici}>
              {secenekler.map((secenek) => <option key={secenek.deger} value={secenek.deger}>{secenek.etiket}</option>)}
            </select>
          ) : <span className="image-create__provider">{secenekler[0]?.etiket ?? "Sağlayıcı yok"}</span>}
          <button className="image-create__submit" disabled={!client || !istem.trim() || calisiyor || !secenekler.length} type="submit">
            {calisiyor ? "Oluşturuluyor…" : "Oluştur"}
          </button>
        </div>
      </form>

      {!gorseller.length && !calisiyor && (
        <div className="image-create__ideas" aria-label="Örnek istemler">
          {ORNEKLER.map((ornek) => (
            <button key={ornek} onClick={() => { setIstem(ornek); kutuRef.current?.focus(); }} type="button">{ornek}</button>
          ))}
        </div>
      )}

      {calisiyor && (
        <div className="image-create__status" role="status">
          <span className="image-create__spinner" aria-hidden="true" />
          Görsel hazırlanıyor · {gecen} sn <small>Genelde 15-60 saniye sürer.</small>
        </div>
      )}
      {hata && <p className="image-create__error" role="alert">{hata}</p>}

      {gorseller.length > 0 && (
        <ul className="image-create__grid" aria-label="Oluşturulan görseller">
          {gorseller.map((gorsel) => {
            const adres = toUrl(gorsel.yol);
            return (
              <li className="image-create__card" key={gorsel.yol}>
                {adres ? <img alt={gorsel.istem} height={gorsel.yukseklik} src={adres} width={gorsel.genislik} /> : <div className="image-create__noimg">{gorsel.yol}</div>}
                <div className="image-create__meta">
                  <p title={gorsel.istem}>{gorsel.istem}</p>
                  <div>
                    <small>{gorsel.saglayici} · {gorsel.genislik}×{gorsel.yukseklik}</small>
                    <button onClick={() => void reveal(gorsel.yol)} type="button">Finder'da göster</button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
