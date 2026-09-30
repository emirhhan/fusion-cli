import { useCallback, useEffect, useState } from "react";
import { Icon } from "../ui/Icon";
import { assetUrl } from "../platform/assetUrl";
import { saveImageAs } from "../platform/dialog";
import { akisSorunlari, atalar, baslangicAkisi, DUGUM_ETIKETI, ORANLAR, dugumGuncelle, kaydedilebilir, sonrakiDugumEkle, type Akis, type DugumTuru, type Islem } from "./akis";
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
  const [basitAkis, setBasitAkis] = useState<Akis>(() => baslangicAkisi());
  const [galeri, setGaleri] = useState<UretilenGorsel[]>([]);
  const [kayitlilar, setKayitlilar] = useState<KayitliAkis[]>([]);
  const [calisiyor, setCalisiyor] = useState(false);
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [secimIcin, setSecimIcin] = useState<string | null>(null);
  const [mod, setMod] = useState<"basit" | "akis">("basit");
  const [hedef, setHedef] = useState<string | null>(null);
  /** Büyük görüntüleyicide açık görselin galerideki sırası. */
  const [acik, setAcik] = useState<number | null>(null);

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
      setBasitAkis((mevcut) => ({
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

  const calistir = async (dalHedefi: string | null = null) => {
    const calisacakAkis = mod === "basit" ? basitAkis : akis;
    const guncelle = mod === "basit" ? setBasitAkis : setAkis;
    const kapsam = dalHedefi ? new Set([...atalar(calisacakAkis, dalHedefi), dalHedefi]) : null;
    const dogrulanacak = kapsam ? {
      ...calisacakAkis,
      dugumler: calisacakAkis.dugumler.filter((dugum) => kapsam.has(dugum.id)),
      baglantilar: calisacakAkis.baglantilar.filter((baglanti) => kapsam.has(baglanti.kaynak) && kapsam.has(baglanti.hedef)),
    } : calisacakAkis;
    const sorunlar = akisSorunlari(dogrulanacak);
    if (sorunlar.length) { setBilgi(sorunlar[0]); return; }
    setCalisiyor(true);
    setBilgi(null);
    try {
      const son = await akisiCalistir(calisacakAkis, istek, (guncel, yeni) => {
        guncelle(guncel);
        if (yeni.length) setGaleri((onceki) => [...yeni, ...onceki]);
      }, mod === "basit" ? { hedef: "uret-1" } : dalHedefi ? { hedef: dalHedefi } : {});
      const hata = son.dugumler.find((dugum) => dugum.durum === "hata" && (!kapsam || kapsam.has(dugum.id)));
      setBilgi(hata ? `${DUGUM_ETIKETI[hata.tur]}: ${hata.hata}` : dalHedefi
        ? "Seçili dal tamamlandı; sonuçlar galeride."
        : "Akış tamamlandı; sonuçlar galeride.");
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
    if (sonuc.ok === true && sonuc.akis && typeof sonuc.akis === "object") {
      setAkis(sonuc.akis as Akis);
      setHedef(null);
    } else setBilgi("Akış açılamadı.");
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

  const sonucUzerindenDevamEt = (yol: string, tur: Islem) => {
    const kaynak = akis.dugumler.find((dugum) => dugum.yol === yol);
    const yeniKaynakId = `gorsel-${Date.now().toString(36)}-${akis.dugumler.length}`;
    const kaynakId = kaynak?.id ?? yeniKaynakId;
    const taban: Akis = kaynak ? akis : {
      ...akis,
      dugumler: [...akis.dugumler, { id: yeniKaynakId, tur: "gorsel", yol, x: 40, y: 400 }],
    };
    const saglayici = secenekler.find((item) => item.referans)?.deger;
    const devam = sonrakiDugumEkle(taban, kaynakId, tur, saglayici);
    const metinId = `metin-${Date.now().toString(36)}-${devam.akis.dugumler.length}`;
    setAkis(tur === "duzenle" ? {
      ...devam.akis,
      dugumler: [...devam.akis.dugumler, { id: metinId, tur: "metin", istem: "", x: 40, y: 300 }],
      baglantilar: [...devam.akis.baglantilar, { kaynak: metinId, hedef: devam.id }],
    } : devam.akis);
    setHedef(devam.id);
    setMod("akis");
    setBilgi(`${DUGUM_ETIKETI[tur]} düğümü eklendi. Talimatı ve sağlayıcıyı kontrol edip akışı çalıştır.`);
  };

  const basitIstem = basitAkis.dugumler.find((dugum) => dugum.id === "metin-1")?.istem ?? "";
  const acikGorsel = acik !== null ? galeri[acik] : undefined;

  /** Galeri kutucuğunun ve görüntüleyicinin ortak eylemleri. */
  const eylemler = (yol: string) => (
    <>
      {secimIcin && <button aria-label="Düğüme kullan" className="image-create__act image-create__act--text" onClick={() => galeridenSec(yol)} title="Düğüme kullan" type="button">Düğüme kullan</button>}
      <button aria-label="İndir" className="image-create__act" onClick={() => void indir(yol)} title="İndir" type="button"><Icon name="download" size={18} /></button>
      <button aria-label="Varyasyonla devam et" className="image-create__act" onClick={() => { setAcik(null); sonucUzerindenDevamEt(yol, "varyasyon"); }} title="Varyasyon" type="button"><Icon name="sparkle" size={18} /></button>
      <button aria-label="Büyüterek devam et" className="image-create__act" onClick={() => { setAcik(null); sonucUzerindenDevamEt(yol, "buyut"); }} title="Büyüt" type="button"><Icon name="expand" size={18} /></button>
      <button aria-label="Düzenleyerek devam et" className="image-create__act" onClick={() => { setAcik(null); sonucUzerindenDevamEt(yol, "duzenle"); }} title="Düzenle" type="button"><Icon name="edit" size={18} /></button>
    </>
  );

  return (
    <section aria-label="Görsel oluştur" className="image-create" data-mode={mod}>
      {/* Sayfa başlığı kabuğun üst çubuğunda; burada yalnız kip seçici durur. */}
      <header className="image-create__top">
        <div aria-label="Görsel oluşturma modu" className="image-create__modes" role="group">
          <button aria-pressed={mod === "basit"} onClick={() => setMod("basit")} type="button">Basit oluştur</button>
          <button aria-pressed={mod === "akis"} onClick={() => setMod("akis")} type="button">İş akışı</button>
        </div>
      </header>
      {mod === "akis" && <>
      <div aria-label="Akış araçları" className="image-create__toolbar" role="toolbar">
        <input aria-label="Akış adı" onChange={(event) => setAkis({ ...akis, ad: event.target.value })} value={akis.ad} />
        <select aria-label="Kayıtlı akışlar" onChange={(event) => void yukle(event.target.value)} value="">
          <option value="">Kayıtlı akışlar</option>
          {kayitlilar.map((item) => <option key={item.id} value={item.id}>{item.ad}</option>)}
        </select>
        <button disabled={calisiyor} onClick={() => { setAkis(baslangicAkisi(secenekler[0]?.deger)); setHedef(null); }} type="button">Yeni</button>
        <button disabled={calisiyor || !client} onClick={() => void kaydet()} type="button">Kaydet</button>
        <button className="image-create__run" disabled={calisiyor || !client} onClick={() => void calistir(hedef)} type="button">
          {calisiyor ? "Çalışıyor…" : "Çalıştır"}
        </button>
        {hedef && <button disabled={calisiyor || !client} onClick={() => void calistir()} type="button">Tüm akışı çalıştır</button>}
      </div>
      </>}
      {!secenekler.length && client && (
        <p className="image-create__error" role="alert">Görsel üretebilen bağlı sağlayıcı yok. Ayarlar → Sağlayıcılar'dan NVIDIA NIM anahtarı ekle ya da Gemini web'e bağlan.</p>
      )}
      {bilgi && <p className="image-create__info" role="status">{bilgi}</p>}
      <div className="image-create__workspace">
        {mod === "akis" && <div className="image-create__canvas">
        {/* Flora'daki gibi düğüm paleti tuvalin üstünde yüzer. */}
        <div aria-label="Düğüm ekle" className="image-create__add" role="group">
          {EKLENEBILIR.map((tur) => (
            <button disabled={calisiyor} key={tur} onClick={() => dugumEkle(tur)} type="button">+ {DUGUM_ETIKETI[tur]}</button>
          ))}
        </div>
        <AkisTuvali
          akis={akis}
          calisiyor={calisiyor}
          onChange={setAkis}
          onGorselSec={(id) => { setSecimIcin(id); setBilgi("Galeriden bir görsel seç."); }}
          onIndir={(yol) => void indir(yol)}
          secenekler={secenekler}
          toUrl={toUrl}
        />
        </div>}
        <aside aria-label="Galeri" className="image-create__gallery">
          {mod === "akis" && <h2>Galeri</h2>}
          {!galeri.length && !calisiyor && (
            <div className="image-create__empty">
              <strong>Hayal et, Fusion çizsin.</strong>
              <p>Üretilen görseller burada kalır; "İndir" demeden diske kaydedilmez.</p>
            </div>
          )}
          <ul className="image-create__grid">
            {calisiyor && mod === "basit" && <li aria-label="Üretiliyor" className="image-create__tile image-create__tile--loading" />}
            {galeri.map((gorsel, sira) => {
              const adres = toUrl(gorsel.yol);
              return (
                <li className="image-create__tile" key={gorsel.yol}>
                  <button aria-label={`${gorsel.istem || "Görsel"} büyük aç`} className="image-create__open" onClick={() => setAcik(sira)} type="button">
                    {adres ? <img alt={gorsel.istem || "Üretilen görsel"} loading="lazy" src={adres} /> : <div className="image-create__noimg">{gorsel.yol.split("/").pop()}</div>}
                  </button>
                  <div className="image-create__overlay">
                    <p>{gorsel.istem}</p>
                    <div className="image-create__acts">{eylemler(gorsel.yol)}</div>
                  </div>
                </li>
              );
            })}
          </ul>
        </aside>
      </div>
      {mod === "basit" && (
        <div className="image-create__prompt">
          <textarea
            aria-label="Nasıl bir görsel istiyorsun?"
            onChange={(event) => setBasitAkis(dugumGuncelle(basitAkis, "metin-1", { istem: event.target.value }))}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (!calisiyor && client && basitIstem.trim()) void calistir();
              }
            }}
            placeholder="Hayal ettiğin görseli tarif et…"
            rows={2}
            value={basitIstem}
          />
          <div className="image-create__prompt-bar">
            <select aria-label="Görsel modeli" onChange={(event) => setBasitAkis(dugumGuncelle(basitAkis, "uret-1", { saglayici: event.target.value }))} value={basitAkis.dugumler.find((dugum) => dugum.id === "uret-1")?.saglayici ?? ""}>
              <option value="">Model seç</option>
              {secenekler.map((item) => <option key={item.deger} value={item.deger}>{item.etiket}</option>)}
            </select>
            <div aria-label="En-boy oranı" className="image-create__ratios" role="radiogroup">
              {ORANLAR.map((oran) => {
                const secili = (basitAkis.dugumler.find((dugum) => dugum.id === "uret-1")?.oran ?? "1:1") === oran;
                const [en, boy] = oran.split(":").map(Number);
                return (
                  <button aria-checked={secili} aria-label={oran} key={oran} onClick={() => setBasitAkis(dugumGuncelle(basitAkis, "uret-1", { oran }))} role="radio" title={`En-boy oranı ${oran}`} type="button">
                    <span aria-hidden="true" className="image-create__ratio-box" style={{ aspectRatio: `${en} / ${boy}` }} />
                    {oran}
                  </button>
                );
              })}
            </div>
            <button aria-label="Görsel oluştur" className="image-create__go" disabled={calisiyor || !client} onClick={() => void calistir()} title={calisiyor ? "Üretiliyor…" : "Görsel oluştur"} type="button">
              {calisiyor ? <span className="image-create__spinner" /> : <Icon name="arrowUp" size={18} />}
            </button>
          </div>
        </div>
      )}
      {acikGorsel && (
        <div aria-label="Görsel görüntüleyici" aria-modal="true" className="image-create__viewer" onKeyDown={(event) => {
          if (event.key === "Escape") setAcik(null);
          if (event.key === "ArrowRight" && acik !== null) setAcik(Math.min(galeri.length - 1, acik + 1));
          if (event.key === "ArrowLeft" && acik !== null) setAcik(Math.max(0, acik - 1));
        }} role="dialog" tabIndex={-1} ref={(element) => element?.focus()}>
          <button aria-label="Görüntüleyiciyi kapat" className="image-create__viewer-close" onClick={() => setAcik(null)} type="button"><Icon name="close" size={20} /></button>
          <div className="image-create__viewer-stage" onClick={() => setAcik(null)}>
            {toUrl(acikGorsel.yol) && <img alt="" onClick={(event) => event.stopPropagation()} src={toUrl(acikGorsel.yol) ?? undefined} />}
          </div>
          <aside className="image-create__viewer-side">
            <h2>İstem</h2>
            <p>{acikGorsel.istem || "İstem kaydı yok."}</p>
            <dl>
              <dt>Model</dt><dd>{acikGorsel.saglayici || "—"}</dd>
              {acikGorsel.genislik > 0 && <><dt>Boyut</dt><dd>{acikGorsel.genislik}×{acikGorsel.yukseklik}</dd></>}
            </dl>
            <button className="image-create__reuse" onClick={() => { setBasitAkis(dugumGuncelle(basitAkis, "metin-1", { istem: acikGorsel.istem })); setMod("basit"); setAcik(null); }} type="button">İstemi yeniden kullan</button>
            <div className="image-create__acts image-create__acts--side">{eylemler(acikGorsel.yol)}</div>
          </aside>
        </div>
      )}
    </section>
  );
}
