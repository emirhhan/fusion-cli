import { useRef, useState, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from "react";
import {
  baglanabilir,
  ciktiTuru,
  DUGUM_ETIKETI,
  dugumGuncelle,
  dugumSil,
  girdiler,
  islemMi,
  MAX_ADET,
  type Akis,
  type Dugum,
} from "./akis";

export interface SaglayiciSecenegi {
  deger: string;
  etiket: string;
  /** Sağlayıcı referans görsel alabiliyor mu (varyasyon, büyütme, düzenleme için gerekli). */
  referans: boolean;
}

export interface AkisTuvaliProps {
  akis: Akis;
  secenekler: SaglayiciSecenegi[];
  calisiyor: boolean;
  onChange: (akis: Akis) => void;
  onGorselSec: (dugumId: string) => void;
  onIndir: (yol: string) => void;
  toUrl: (path: string) => string | null;
}

/** Düğüm kartının genişliği (px); bağlantı uçları bu değerden hesaplanır. */
const DUGUM_GENISLIK = 220;
/** Port merkezinin kart üstünden uzaklığı (px): başlık satırının ortası. */
const PORT_Y = 22;
/** Yakınlaştırma sınırları ve adımı: %40'ın altında kart metni okunmaz, %200 üstü kartı ekrandan taşırır. */
const MIN_OLCEK = 0.4;
const MAX_OLCEK = 2;
const OLCEK_ADIMI = 0.1;

interface Gorunum { x: number; y: number; olcek: number }

function sinirla(olcek: number): number {
  return Math.min(MAX_OLCEK, Math.max(MIN_OLCEK, Math.round(olcek * 100) / 100));
}

/** Bu işlem referans görsel gerektiriyor mu? Üret yalnız görsel bağlıysa gerektirir. */
function referansGerekir(akis: Akis, dugum: Dugum): boolean {
  if (dugum.tur === "uret") return girdiler(akis, dugum.id).gorsel !== undefined;
  return islemMi(dugum.tur);
}

function bezierYolu(x1: number, y1: number, x2: number, y2: number): string {
  const orta = Math.max(40, Math.abs(x2 - x1) / 2);
  return `M ${x1} ${y1} C ${x1 + orta} ${y1}, ${x2 - orta} ${y2}, ${x2} ${y2}`;
}

function DugumGovdesi({ akis, dugum, props }: { akis: Akis; dugum: Dugum; props: AkisTuvaliProps }) {
  const guncelle = (degisim: Partial<Dugum>) => props.onChange(dugumGuncelle(akis, dugum.id, degisim));
  const onizleme = dugum.tur === "cikti" ? girdiler(akis, dugum.id).gorsel?.yol : dugum.yol;
  const adres = onizleme ? props.toUrl(onizleme) : null;
  const uygun = props.secenekler.filter((secenek) => !referansGerekir(akis, dugum) || secenek.referans);
  const varyasyonlar = dugum.sonuclar ?? [];
  return (
    <div className="akis-dugum__govde" onPointerDown={(event) => event.stopPropagation()}>
      {dugum.tur === "metin" && (
        <textarea
          aria-label="Metin istemi"
          disabled={props.calisiyor}
          onChange={(event) => guncelle({ istem: event.target.value })}
          placeholder="Ne görmek istediğini anlat…"
          rows={4}
          value={dugum.istem ?? ""}
        />
      )}
      {islemMi(dugum.tur) && (
        <>
          <select
            aria-label={`${DUGUM_ETIKETI[dugum.tur]} sağlayıcısı`}
            disabled={props.calisiyor}
            onChange={(event) => guncelle({ saglayici: event.target.value })}
            value={dugum.saglayici ?? ""}
          >
            <option value="">Sağlayıcı seç</option>
            {uygun.map((secenek) => <option key={secenek.deger} value={secenek.deger}>{secenek.etiket}</option>)}
          </select>
          {dugum.tur !== "buyut" && (
            <input
              aria-label="Ek talimat"
              disabled={props.calisiyor}
              onChange={(event) => guncelle({ istem: event.target.value })}
              placeholder={dugum.tur === "duzenle" ? "Nasıl düzenlensin? (Metin girdisine eklenir)" : "Ek talimat (isteğe bağlı)"}
              value={dugum.istem ?? ""}
            />
          )}
          <label className="akis-dugum__adet">
            Varyasyon
            <select
              aria-label={`${DUGUM_ETIKETI[dugum.tur]} varyasyon sayısı`}
              disabled={props.calisiyor}
              onChange={(event) => guncelle({ adet: Number(event.target.value) })}
              value={dugum.adet ?? 1}
            >
              {Array.from({ length: MAX_ADET }, (_, index) => index + 1).map((adet) => (
                <option key={adet} value={adet}>{adet}</option>
              ))}
            </select>
          </label>
          {referansGerekir(akis, dugum) && !uygun.length && (
            <p className="akis-dugum__uyari">Referans görsel alabilen bağlı sağlayıcı yok (Gemini web gerekli).</p>
          )}
        </>
      )}
      {dugum.tur === "gorsel" && (
        <button disabled={props.calisiyor} onClick={() => props.onGorselSec(dugum.id)} type="button">
          {dugum.yol ? "Görseli değiştir" : "Galeriden seç"}
        </button>
      )}
      {varyasyonlar.length > 1 ? (
        <div aria-label="Varyasyonlar" className="akis-dugum__varyasyonlar" role="radiogroup">
          {varyasyonlar.map((yol, index) => {
            const kucuk = props.toUrl(yol);
            return (
              <button
                aria-checked={yol === dugum.yol}
                aria-label={`Varyasyon ${index + 1}`}
                key={yol}
                onClick={() => guncelle({ yol })}
                role="radio"
                type="button"
              >
                {kucuk ? <img alt="" src={kucuk} /> : <span>{index + 1}</span>}
              </button>
            );
          })}
        </div>
      ) : (
        adres && <img alt={`${DUGUM_ETIKETI[dugum.tur]} sonucu`} className="akis-dugum__onizleme" src={adres} />
      )}
      {onizleme && !adres && varyasyonlar.length <= 1 && <p className="akis-dugum__yol">{onizleme.split("/").pop()}</p>}
      {dugum.tur === "cikti" && onizleme && (
        <button onClick={() => props.onIndir(onizleme)} type="button">İndir</button>
      )}
      {dugum.durum === "calisiyor" && <p className="akis-dugum__durum" role="status">Üretiliyor…</p>}
      {dugum.hata && <p className="akis-dugum__hata" role="alert">{dugum.hata}</p>}
    </div>
  );
}

export function AkisTuvali(props: AkisTuvaliProps) {
  const { akis, onChange } = props;
  const [bekleyenKaynak, setBekleyenKaynak] = useState<string | null>(null);
  const [gorunum, setGorunum] = useState<Gorunum>({ x: 0, y: 0, olcek: 1 });
  const [cekilen, setCekilen] = useState<{ kaynak: string; x: number; y: number } | null>(null);
  const kutu = useRef<HTMLDivElement>(null);
  const hareket = useRef<
    | { tur: "dugum"; id: string; dx: number; dy: number }
    | { tur: "sahne"; bx: number; by: number; gx: number; gy: number }
    | null
  >(null);

  /** Ekran koordinatını sahne (düğüm) koordinatına çevir. */
  const sahneNoktasi = (clientX: number, clientY: number) => {
    const kutuyer = kutu.current?.getBoundingClientRect();
    const solx = kutuyer?.left ?? 0;
    const ustY = kutuyer?.top ?? 0;
    return { x: (clientX - solx - gorunum.x) / gorunum.olcek, y: (clientY - ustY - gorunum.y) / gorunum.olcek };
  };

  const baglantiEkle = (kaynakId: string, hedefId: string) => {
    if (baglanabilir(akis, kaynakId, hedefId)) {
      onChange({ ...akis, baglantilar: [...akis.baglantilar, { kaynak: kaynakId, hedef: hedefId }] });
    }
  };

  const tuvalBasla = (event: ReactPointerEvent<HTMLDivElement>) => {
    const hedef = event.target as HTMLElement;
    if (hedef.closest(".akis-dugum")) return;
    hareket.current = { tur: "sahne", bx: event.clientX, by: event.clientY, gx: gorunum.x, gy: gorunum.y };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const tuvalHareket = (event: ReactPointerEvent<HTMLDivElement>) => {
    const aktif = hareket.current;
    if (cekilen) {
      const nokta = sahneNoktasi(event.clientX, event.clientY);
      setCekilen({ ...cekilen, ...nokta });
      return;
    }
    if (!aktif) return;
    if (aktif.tur === "sahne") {
      setGorunum({ ...gorunum, x: aktif.gx + event.clientX - aktif.bx, y: aktif.gy + event.clientY - aktif.by });
      return;
    }
    const nokta = sahneNoktasi(event.clientX, event.clientY);
    onChange(dugumGuncelle(akis, aktif.id, { x: Math.max(0, nokta.x - aktif.dx), y: Math.max(0, nokta.y - aktif.dy) }));
  };
  const tuvalBitir = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (cekilen) {
      // Bırakılan noktanın altındaki giriş portu ya da düğüm bağlantının hedefidir.
      const altindaki = document.elementFromPoint?.(event.clientX, event.clientY) as HTMLElement | null;
      const hedefId = altindaki?.closest<HTMLElement>("[data-dugum-id]")?.dataset.dugumId;
      if (hedefId) baglantiEkle(cekilen.kaynak, hedefId);
      setCekilen(null);
    }
    hareket.current = null;
  };
  const tekerlek = (event: ReactWheelEvent<HTMLDivElement>) => {
    // Yalnız Ctrl/⌘ ile yakınlaştırılır; düz tekerlek sayfanın normal kaydırmasıdır.
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    setGorunum({ ...gorunum, olcek: sinirla(gorunum.olcek - Math.sign(event.deltaY) * OLCEK_ADIMI) });
  };

  const cekilenKaynak = cekilen ? akis.dugumler.find((dugum) => dugum.id === cekilen.kaynak) : undefined;

  return (
    <div
      aria-label="Görsel iş akışı tuvali"
      className="akis-tuvali"
      data-surukleniyor={hareket.current?.tur === "sahne" ? "true" : undefined}
      onPointerDown={tuvalBasla}
      onPointerMove={tuvalHareket}
      onPointerUp={tuvalBitir}
      onWheel={tekerlek}
      ref={kutu}
      role="region"
    >
      <div aria-label="Yakınlaştırma" className="akis-tuvali__olcek" onPointerDown={(event) => event.stopPropagation()} role="group">
        <button aria-label="Uzaklaştır" onClick={() => setGorunum({ ...gorunum, olcek: sinirla(gorunum.olcek - OLCEK_ADIMI) })} type="button">−</button>
        <button aria-label="Görünümü sıfırla" onClick={() => setGorunum({ x: 0, y: 0, olcek: 1 })} type="button">{Math.round(gorunum.olcek * 100)}%</button>
        <button aria-label="Yakınlaştır" onClick={() => setGorunum({ ...gorunum, olcek: sinirla(gorunum.olcek + OLCEK_ADIMI) })} type="button">+</button>
      </div>
      <div
        className="akis-tuvali__sahne"
        style={{ transform: `translate(${gorunum.x}px, ${gorunum.y}px) scale(${gorunum.olcek})` }}
      >
        <svg aria-hidden="false" className="akis-tuvali__baglantilar">
          {akis.baglantilar.map((baglanti) => {
            const kaynak = akis.dugumler.find((dugum) => dugum.id === baglanti.kaynak);
            const hedef = akis.dugumler.find((dugum) => dugum.id === baglanti.hedef);
            if (!kaynak || !hedef) return null;
            return (
              <path
                aria-label={`${DUGUM_ETIKETI[kaynak.tur]} → ${DUGUM_ETIKETI[hedef.tur]} bağlantısını sil`}
                className="akis-tuvali__baglanti"
                d={bezierYolu(kaynak.x + DUGUM_GENISLIK, kaynak.y + PORT_Y, hedef.x, hedef.y + PORT_Y)}
                key={`${baglanti.kaynak}-${baglanti.hedef}`}
                onClick={() => onChange({ ...akis, baglantilar: akis.baglantilar.filter((item) => item !== baglanti) })}
                role="button"
              />
            );
          })}
          {cekilen && cekilenKaynak && (
            <path
              className="akis-tuvali__baglanti akis-tuvali__baglanti--gecici"
              d={bezierYolu(cekilenKaynak.x + DUGUM_GENISLIK, cekilenKaynak.y + PORT_Y, cekilen.x, cekilen.y)}
            />
          )}
        </svg>
        {akis.dugumler.map((dugum) => (
          <article
            aria-label={`${DUGUM_ETIKETI[dugum.tur]} düğümü`}
            className="akis-dugum"
            data-dugum-id={dugum.id}
            data-durum={dugum.durum ?? "bos"}
            data-tur={dugum.tur}
            key={dugum.id}
            style={{ left: dugum.x, top: dugum.y, width: DUGUM_GENISLIK }}
          >
            <header
              className="akis-dugum__baslik"
              onPointerDown={(event) => {
                event.stopPropagation();
                const nokta = sahneNoktasi(event.clientX, event.clientY);
                hareket.current = { tur: "dugum", id: dugum.id, dx: nokta.x - dugum.x, dy: nokta.y - dugum.y };
                kutu.current?.setPointerCapture?.(event.pointerId);
              }}
            >
              {dugum.tur !== "metin" && dugum.tur !== "gorsel" && (
                <button
                  aria-label={`${DUGUM_ETIKETI[dugum.tur]} girdisine bağla`}
                  className="akis-dugum__port akis-dugum__port--giris"
                  data-bekliyor={(bekleyenKaynak ?? cekilen?.kaynak) && baglanabilir(akis, (bekleyenKaynak ?? cekilen?.kaynak) as string, dugum.id) ? "true" : undefined}
                  onClick={() => {
                    if (bekleyenKaynak) baglantiEkle(bekleyenKaynak, dugum.id);
                    setBekleyenKaynak(null);
                  }}
                  onPointerDown={(event) => event.stopPropagation()}
                  type="button"
                />
              )}
              <span>{DUGUM_ETIKETI[dugum.tur]}</span>
              <button
                aria-label={`${DUGUM_ETIKETI[dugum.tur]} düğümünü sil`}
                className="akis-dugum__sil"
                disabled={props.calisiyor}
                onClick={() => onChange(dugumSil(akis, dugum.id))}
                onPointerDown={(event) => event.stopPropagation()}
                type="button"
              >×</button>
              {ciktiTuru(dugum.tur) && (
                <button
                  aria-label={`${DUGUM_ETIKETI[dugum.tur]} çıkışından bağlantı başlat`}
                  aria-pressed={bekleyenKaynak === dugum.id}
                  className="akis-dugum__port akis-dugum__port--cikis"
                  onClick={() => setBekleyenKaynak((mevcut) => (mevcut === dugum.id ? null : dugum.id))}
                  onPointerDown={(event) => {
                    // Porttan sürükleyince geçici bir bağlantı çizilir; bırakılan
                    // düğüme bağlanır. Tıklayıp bırakmak klavye dostu yolu korur.
                    event.stopPropagation();
                    setCekilen({ kaynak: dugum.id, ...sahneNoktasi(event.clientX, event.clientY) });
                    kutu.current?.setPointerCapture?.(event.pointerId);
                  }}
                  type="button"
                />
              )}
            </header>
            <DugumGovdesi akis={akis} dugum={dugum} props={props} />
          </article>
        ))}
      </div>
    </div>
  );
}
