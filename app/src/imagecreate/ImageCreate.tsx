import { useCallback, useEffect, useState } from "react";
import { assetUrl } from "../platform/assetUrl";
import { saveImageAs } from "../platform/dialog";
import { akisSorunlari, baslangicAkisi, DUGUM_ETIKETI, dugumGuncelle, kaydedilebilir, type Akis, type DugumTuru } from "./akis";
import { akisiCalistir, type UretilenGorsel } from "./akisCalistir";
import { AkisTuvali, type SaglayiciSecenegi } from "./AkisTuvali";
import "./ImageCreate.css";

export type { UretilenGorsel } from "./akisCalistir";

interface ImageClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

interface KayitliAkis { id: string; ad: string }

export interface ImageCreateProps {
  client: ImageClient | null;
  /** Test ve önizleme için: yerel yolu gösterilebilir adrese çevirir. */
  toUrl?: (path: string) => string | null;
  /** "İndir": kullanıcıya kayıt yeri sorar; iptalde `null`. */
  chooseSavePath?: (defaultName: string) => Promise<string | null>;
}

const EKLENEBILIR: DugumTuru[] = ["metin", "gorsel", "uret", "varyasyon", "buyut", "duzenle", "cikti"];

function secenekleriOku(sonuc: Record<string, unknown>): SaglayiciSecenegi[] {
  const ham = Array.isArray(sonuc.secenekler) ? (sonuc.secenekler as Record<string, unknown>[]) : [];
  return ham.map((item) => ({ deger: String(item.deger), etiket: String(item.etiket), referans: item.referans === true }));
}

/**
 * Görsel oluştur — Flora benzeri düğümlü iş akışı.
 *
 * Üretilen görseller uygulama içi galeride kalır; Finder'a ya da Resimler'e
 * kendiliğinden inmez. Yalnız "İndir"e basınca kullanıcının seçtiği yere kopyalanır.
 */
export function ImageCreate({ client, toUrl = assetUrl, chooseSavePath = saveImageAs }: ImageCreateProps) {
  const [secenekler, setSecenekler] = useState<SaglayiciSecenegi[]>([]);
  const [akis, setAkis] = useState<Akis>(() => baslangicAkisi());
  const [galeri, setGaleri] = useState<UretilenGorsel[]>([]);
  const [kayitlilar, setKayitlilar] = useState<KayitliAkis[]>([]);
  const [calisiyor, setCalisiyor] = useState(false);
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [secimIcin, setSecimIcin] = useState<string | null>(null);

  const istek = useCallback(async (name: string, data: Record<string, unknown>) => {
    if (!client) throw new Error("Çekirdek bağlı değil.");
    return client.request(name, data);
  }, [client]);

  useEffect(() => {
    if (!client) return;
    let iptal = false;
    void istek("gorsel.saglayicilar", {}).then((sonuc) => {
      if (iptal) return;
      const liste = secenekleriOku(sonuc);
      setSecenekler(liste);
      const varsayilan = liste[0]?.deger ?? "";
      setAkis((mevcut) => ({
        ...mevcut,
        dugumler: mevcut.dugumler.map((dugum) => (dugum.tur === "uret" && !dugum.saglayici ? { ...dugum, saglayici: varsayilan } : dugum)),
      }));
    }).catch(() => undefined);
    void istek("gorsel.galeri", {}).then((sonuc) => {
      if (iptal || !Array.isArray(sonuc.dosyalar)) return;
      setGaleri((sonuc.dosyalar as Record<string, unknown>[]).map((dosya) => ({
        yol: String(dosya.yol), genislik: Number(dosya.genislik ?? 0), yukseklik: Number(dosya.yukseklik ?? 0),
        istem: String(dosya.istem ?? ""), saglayici: String(dosya.saglayici ?? ""),
      })));
    }).catch(() => undefined);
    void istek("gorsel.akislar", {}).then((sonuc) => {
      if (!iptal && Array.isArray(sonuc.akislar)) setKayitlilar(sonuc.akislar as KayitliAkis[]);
    }).catch(() => undefined);
    return () => { iptal = true; };
  }, [client, istek]);

  const dugumEkle = (tur: DugumTuru) => {
    const sira = akis.dugumler.length;
    const id = `${tur}-${Date.now().toString(36)}`;
    const saglayici = tur === "uret" ? secenekler[0]?.deger : secenekler.find((item) => item.referans)?.deger;
    setAkis({
      ...akis,
      dugumler: [...akis.dugumler, { id, tur, x: 40 + (sira % 4) * 240, y: 260 + Math.floor(sira / 4) * 40, saglayici }],
    });
  };

  const calistir = async () => {
    const sorunlar = akisSorunlari(akis);
    if (sorunlar.length) { setBilgi(sorunlar[0]); return; }
    setCalisiyor(true);
    setBilgi(null);
    try {
      const son = await akisiCalistir(akis, istek, (guncel, yeni) => {
        setAkis(guncel);
        if (yeni.length) setGaleri((onceki) => [...yeni, ...onceki]);
      });
      const hata = son.dugumler.find((dugum) => dugum.durum === "hata");
      setBilgi(hata ? `${DUGUM_ETIKETI[hata.tur]}: ${hata.hata}` : "Akış tamamlandı; sonuçlar galeride.");
    } finally {
      setCalisiyor(false);
    }
  };

  const kaydet = async () => {
    try {
      const sonuc = await istek("gorsel.akis.kaydet", { akis: kaydedilebilir(akis) });
      if (sonuc.ok !== true) { setBilgi(String(sonuc.metin ?? "Akış kaydedilemedi.")); return; }
      const id = String(sonuc.id);
      setAkis({ ...akis, id });
      setKayitlilar((onceki) => [{ id, ad: akis.ad }, ...onceki.filter((item) => item.id !== id)]);
      setBilgi("Akış kaydedildi.");
    } catch (reason) {
      setBilgi(`Akış kaydedilemedi: ${String(reason)}`);
    }
  };

  const yukle = async (id: string) => {
    if (!id) return;
    const sonuc = await istek("gorsel.akis.yukle", { id }).catch(() => ({ ok: false }) as Record<string, unknown>);
    if (sonuc.ok === true && sonuc.akis && typeof sonuc.akis === "object") setAkis(sonuc.akis as Akis);
    else setBilgi("Akış açılamadı.");
  };

  const indir = async (yol: string) => {
    const hedef = await chooseSavePath(yol.split("/").pop() ?? "gorsel.png");
    if (!hedef) return;
    const sonuc = await istek("gorsel.kaydet", { yol, hedef }).catch((reason) => ({ ok: false, metin: String(reason) }) as Record<string, unknown>);
    setBilgi(sonuc.ok === true ? `Kaydedildi: ${hedef}` : String(sonuc.metin ?? "Kaydedilemedi."));
  };

  const galeridenSec = (yol: string) => {
    if (!secimIcin) return;
    setAkis(dugumGuncelle(akis, secimIcin, { yol }));
    setSecimIcin(null);
  };

  return (
    <section aria-label="Görsel oluştur" className="image-create">
      <div aria-label="Akış araçları" className="image-create__toolbar" role="toolbar">
        <input aria-label="Akış adı" onChange={(event) => setAkis({ ...akis, ad: event.target.value })} value={akis.ad} />
        <div className="image-create__add">
          {EKLENEBILIR.map((tur) => (
            <button disabled={calisiyor} key={tur} onClick={() => dugumEkle(tur)} type="button">+ {DUGUM_ETIKETI[tur]}</button>
          ))}
        </div>
        <select aria-label="Kayıtlı akışlar" onChange={(event) => void yukle(event.target.value)} value="">
          <option value="">Kayıtlı akışlar</option>
          {kayitlilar.map((item) => <option key={item.id} value={item.id}>{item.ad}</option>)}
        </select>
        <button disabled={calisiyor} onClick={() => setAkis(baslangicAkisi(secenekler[0]?.deger))} type="button">Yeni</button>
        <button disabled={calisiyor || !client} onClick={() => void kaydet()} type="button">Kaydet</button>
        <button className="image-create__run" disabled={calisiyor || !client} onClick={() => void calistir()} type="button">
          {calisiyor ? "Çalışıyor…" : "Çalıştır"}
        </button>
      </div>
      {!secenekler.length && client && (
        <p className="image-create__error" role="alert">Görsel üretebilen bağlı sağlayıcı yok. Ayarlar → Sağlayıcılar'dan NVIDIA NIM anahtarı ekle ya da Gemini web'e bağlan.</p>
      )}
      {bilgi && <p className="image-create__info" role="status">{bilgi}</p>}
      <div className="image-create__workspace">
        <AkisTuvali
          akis={akis}
          calisiyor={calisiyor}
          onChange={setAkis}
          onGorselSec={(id) => { setSecimIcin(id); setBilgi("Galeriden bir görsel seç."); }}
          onIndir={(yol) => void indir(yol)}
          secenekler={secenekler}
          toUrl={toUrl}
        />
        <aside aria-label="Galeri" className="image-create__gallery">
          <h2>Galeri</h2>
          {!galeri.length && <p>Üretilen görseller burada kalır; "İndir" demeden diske kaydedilmez.</p>}
          <ul>
            {galeri.map((gorsel) => {
              const adres = toUrl(gorsel.yol);
              return (
                <li key={gorsel.yol}>
                  {adres ? <img alt={gorsel.istem || "Üretilen görsel"} src={adres} /> : <div className="image-create__noimg">{gorsel.yol.split("/").pop()}</div>}
                  <small>{gorsel.saglayici}{gorsel.genislik ? ` · ${gorsel.genislik}×${gorsel.yukseklik}` : ""}</small>
                  <div>
                    {secimIcin && <button onClick={() => galeridenSec(gorsel.yol)} type="button">Düğüme kullan</button>}
                    <button onClick={() => void indir(gorsel.yol)} type="button">İndir</button>
                  </div>
                </li>
              );
            })}
          </ul>
        </aside>
      </div>
    </section>
  );
}
