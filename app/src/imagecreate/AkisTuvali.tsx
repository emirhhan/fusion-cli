import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  baglanabilir,
  ciktiTuru,
  DUGUM_ETIKETI,
  dugumGuncelle,
  dugumSil,
  girdiler,
  islemMi,
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

/** Bu işlem referans görsel gerektiriyor mu? Üret yalnız görsel bağlıysa gerektirir. */
function referansGerekir(akis: Akis, dugum: Dugum): boolean {
  if (dugum.tur === "uret") return girdiler(akis, dugum.id).gorsel !== undefined;
  return islemMi(dugum.tur);
}

function DugumGovdesi({ akis, dugum, props }: { akis: Akis; dugum: Dugum; props: AkisTuvaliProps }) {
  const guncelle = (degisim: Partial<Dugum>) => props.onChange(dugumGuncelle(akis, dugum.id, degisim));
  const onizleme = dugum.tur === "cikti" ? girdiler(akis, dugum.id).gorsel?.yol : dugum.yol;
  const adres = onizleme ? props.toUrl(onizleme) : null;
  const uygun = props.secenekler.filter((secenek) => !referansGerekir(akis, dugum) || secenek.referans);
  return (
    <div className="akis-dugum__govde">
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
      {adres && <img alt={`${DUGUM_ETIKETI[dugum.tur]} sonucu`} className="akis-dugum__onizleme" src={adres} />}
      {onizleme && !adres && <p className="akis-dugum__yol">{onizleme.split("/").pop()}</p>}
      {dugum.tur === "cikti" && onizleme && (
        <button onClick={() => props.onIndir(onizleme)} type="button">İndir</button>
      )}
      {dugum.durum === "calisiyor" && <p className="akis-dugum__durum" role="status">Üretiliyor…</p>}
      {dugum.durum === "hata" && <p className="akis-dugum__hata" role="alert">{dugum.hata}</p>}
    </div>
  );
}

export function AkisTuvali(props: AkisTuvaliProps) {
  const { akis, onChange } = props;
  const [bekleyenKaynak, setBekleyenKaynak] = useState<string | null>(null);
  const surukleme = useRef<{ id: string; dx: number; dy: number } | null>(null);

  const suruklemeBaslat = (event: ReactPointerEvent, dugum: Dugum) => {
    surukleme.current = { id: dugum.id, dx: event.clientX - dugum.x, dy: event.clientY - dugum.y };
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
  };
  const suruklemeHareket = (event: ReactPointerEvent) => {
    const aktif = surukleme.current;
    if (!aktif) return;
    onChange(dugumGuncelle(akis, aktif.id, {
      x: Math.max(0, event.clientX - aktif.dx),
      y: Math.max(0, event.clientY - aktif.dy),
    }));
  };
  const baglantiBitir = (hedefId: string) => {
    if (!bekleyenKaynak) return;
    if (baglanabilir(akis, bekleyenKaynak, hedefId)) {
      onChange({ ...akis, baglantilar: [...akis.baglantilar, { kaynak: bekleyenKaynak, hedef: hedefId }] });
    }
    setBekleyenKaynak(null);
  };

  return (
    <div className="akis-tuvali" aria-label="Görsel iş akışı tuvali" role="region">
      <svg aria-hidden="false" className="akis-tuvali__baglantilar">
        {akis.baglantilar.map((baglanti) => {
          const kaynak = akis.dugumler.find((dugum) => dugum.id === baglanti.kaynak);
          const hedef = akis.dugumler.find((dugum) => dugum.id === baglanti.hedef);
          if (!kaynak || !hedef) return null;
          const x1 = kaynak.x + DUGUM_GENISLIK;
          const y1 = kaynak.y + PORT_Y;
          const x2 = hedef.x;
          const y2 = hedef.y + PORT_Y;
          const orta = Math.max(40, Math.abs(x2 - x1) / 2);
          return (
            <path
              aria-label={`${DUGUM_ETIKETI[kaynak.tur]} → ${DUGUM_ETIKETI[hedef.tur]} bağlantısını sil`}
              className="akis-tuvali__baglanti"
              d={`M ${x1} ${y1} C ${x1 + orta} ${y1}, ${x2 - orta} ${y2}, ${x2} ${y2}`}
              key={`${baglanti.kaynak}-${baglanti.hedef}`}
              onClick={() => onChange({
                ...akis,
                baglantilar: akis.baglantilar.filter((item) => item !== baglanti),
              })}
              role="button"
            />
          );
        })}
      </svg>
      {akis.dugumler.map((dugum) => (
        <article
          aria-label={`${DUGUM_ETIKETI[dugum.tur]} düğümü`}
          className="akis-dugum"
          data-durum={dugum.durum ?? "bos"}
          data-tur={dugum.tur}
          key={dugum.id}
          style={{ left: dugum.x, top: dugum.y, width: DUGUM_GENISLIK }}
        >
          <header
            className="akis-dugum__baslik"
            onPointerDown={(event) => suruklemeBaslat(event, dugum)}
            onPointerMove={suruklemeHareket}
            onPointerUp={() => { surukleme.current = null; }}
          >
            {dugum.tur !== "metin" && dugum.tur !== "gorsel" && (
              <button
                aria-label={`${DUGUM_ETIKETI[dugum.tur]} girdisine bağla`}
                className="akis-dugum__port akis-dugum__port--giris"
                data-bekliyor={bekleyenKaynak !== null && baglanabilir(akis, bekleyenKaynak, dugum.id) ? "true" : undefined}
                onClick={() => baglantiBitir(dugum.id)}
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
                onPointerDown={(event) => event.stopPropagation()}
                type="button"
              />
            )}
          </header>
          <DugumGovdesi akis={akis} dugum={dugum} props={props} />
        </article>
      ))}
    </div>
  );
}
