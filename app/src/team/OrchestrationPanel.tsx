import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import "./OrchestrationBoard.css";

/**
 * Ajanlar sekmesindeki "Ekipler ve iş akışları" bölümü — `/team` (P-061) ve
 * `/workflows`'un (P-062) masaüstü yüzü. Ekip panosu `/team goster <ad>` ile açılır.
 *
 * Kayıtlı tanımlar `/workflows <ad>` komutuyla ajana verilir (terminaldeki aynı yol);
 * koşan koşu `akis.iptal` ile durdurulur, ayrıntısı `akis.kosu` ile açılır; ekip iki
 * adımlı onayla `ekip.sil` ile silinir. Liste, pano olayı geldikçe yeniden okunur.
 * Bu RPC'leri tanımayan eski yan süreçte bölüm hata göstermeden gizlenir.
 */

interface Tanim { ad: string; kapsam: string; aciklama: string }
interface Ekip { ad: string; hedef: string; gorev: number; tamam: number }
interface Kosu {
  run_id: string;
  name: string;
  status: string;
  agents_started: number;
  nodes: { status: string }[];
  phase: string;
  message: string;
}

interface KosuAyrintisi {
  kimlik: string;
  rapor: string;
  dugumler: { id: string; etiket: string; durum: string; ozet: string }[];
}

const DUGUM_DURUMU: Record<string, string> = {
  bekliyor: "bekliyor", calisiyor: "çalışıyor", tamam: "tamam", basarisiz: "başarısız", iptal: "iptal", atlandi: "atlandı",
};

const DURUM: Record<string, string> = {
  calisiyor: "Çalışıyor", tamam: "Tamamlandı", yarim: "Yarım kaldı", iptal: "İptal edildi", hata: "Hata",
};

/** Panonun yeniden okunmasını tetikleyen olaylar. */
const YENILEYEN = new Set(["WorkflowProgress", "TeamBoardChanged"]);

function tanimlar(yanit: Record<string, unknown>): Tanim[] {
  const ham = Array.isArray(yanit.tanimlar) ? yanit.tanimlar : [];
  return ham.flatMap((item: unknown) => {
    if (!item || typeof item !== "object") return [];
    const { ad, kapsam, aciklama } = item as Record<string, unknown>;
    return typeof ad === "string" && ad ? [{ ad, kapsam: String(kapsam ?? ""), aciklama: String(aciklama ?? "") }] : [];
  });
}

function ekipler(yanit: Record<string, unknown>): Ekip[] {
  const ham = Array.isArray(yanit.ekipler) ? yanit.ekipler : [];
  return ham.flatMap((item: unknown) => {
    if (!item || typeof item !== "object") return [];
    const { ad, hedef, gorev, tamam } = item as Record<string, unknown>;
    return typeof ad === "string" && ad
      ? [{ ad, hedef: String(hedef ?? ""), gorev: Number(gorev) || 0, tamam: Number(tamam) || 0 }]
      : [];
  });
}

/** Eski yan süreç bu RPC'yi tanımıyor mu? (`Bilinmeyen istek: …`) */
function desteklenmiyor(yanit: Record<string, unknown>): boolean {
  return yanit.ok !== true && String(yanit.metin ?? "").startsWith("Bilinmeyen istek");
}

function ayrinti(kimlik: string, yanit: Record<string, unknown>): KosuAyrintisi {
  const kosu = (yanit.kosu && typeof yanit.kosu === "object" ? yanit.kosu : {}) as Record<string, unknown>;
  const ham = Array.isArray(kosu.nodes) ? kosu.nodes : [];
  return {
    kimlik,
    rapor: String(kosu.report ?? ""),
    dugumler: ham.flatMap((item: unknown) => {
      if (!item || typeof item !== "object") return [];
      const { id, label, status, summary } = item as Record<string, unknown>;
      return [{ id: String(id ?? ""), etiket: String(label ?? id ?? ""), durum: String(status ?? ""), ozet: String(summary ?? "") }];
    }),
  };
}

function kosular(yanit: Record<string, unknown>): Kosu[] {
  const ham = Array.isArray(yanit.kosular) ? yanit.kosular : [];
  return ham.filter((item): item is Kosu => !!item && typeof item === "object" && typeof (item as Kosu).run_id === "string");
}

export function OrchestrationPanel({ client, onCommand }: { client: ProtocolClient; onCommand?: (line: string) => void }) {
  const [liste, setListe] = useState<{ tanimlar: Tanim[]; kosular: Kosu[]; ekipler: Ekip[] }>({ tanimlar: [], kosular: [], ekipler: [] });
  const [hata, setHata] = useState<string | null>(null);
  const [silinecek, setSilinecek] = useState<string | null>(null);
  const [acikKosu, setAcikKosu] = useState<KosuAyrintisi | null>(null);
  /** Görülen koşu/ekip durumları: liste yalnız durum DEĞİŞİNCE yeniden okunur (her düğümde değil). */
  const gorulen = useRef(new Map<string, string>());

  const yukle = useCallback(async () => {
    try {
      const [yanit, ekipYaniti] = await Promise.all([client.request("akis.liste", {}), client.request("ekip.liste", {})]);
      const akisYok = desteklenmiyor(yanit);
      const ekipYok = desteklenmiyor(ekipYaniti);
      if (yanit.ok !== true && !akisYok) throw new Error(String(yanit.metin ?? "İş akışları okunamadı."));
      if (ekipYaniti.ok !== true && !ekipYok) throw new Error(String(ekipYaniti.metin ?? "Ekipler okunamadı."));
      setListe({
        tanimlar: akisYok ? [] : tanimlar(yanit),
        kosular: akisYok ? [] : kosular(yanit),
        ekipler: ekipYok ? [] : ekipler(ekipYaniti),
      });
      setHata(null);
    } catch (error) {
      setHata(errorMessage(error));
    }
  }, [client]);

  useEffect(() => { void yukle(); }, [yukle]);
  useEffect(() => client.onEvent((event) => {
    if (typeof event.olay !== "string" || !YENILEYEN.has(event.olay)) return;
    const kimlik = String(event.run_id ?? event.team ?? "");
    const durum = String(event.status ?? "");
    if (gorulen.current.get(kimlik) === durum) return;
    gorulen.current.set(kimlik, durum);
    void yukle();
  }), [client, yukle]);

  const iptal = async (kimlik: string) => {
    try {
      const yanit = await client.request("akis.iptal", { kimlik });
      if (yanit.ok !== true) throw new Error(String(yanit.metin ?? "Koşu durdurulamadı."));
      await yukle();
    } catch (error) {
      setHata(errorMessage(error));
    }
  };

  const sil = async (ad: string) => {
    try {
      const yanit = await client.request("ekip.sil", { ad });
      if (yanit.ok !== true) throw new Error(String(yanit.metin ?? "Ekip silinemedi."));
      setSilinecek(null);
      await yukle();
    } catch (error) {
      setHata(errorMessage(error));
    }
  };

  const ayrintiAc = async (kimlik: string) => {
    if (acikKosu?.kimlik === kimlik) {
      setAcikKosu(null);
      return;
    }
    try {
      const yanit = await client.request("akis.kosu", { kimlik });
      if (yanit.ok !== true) throw new Error(String(yanit.metin ?? "Koşu okunamadı."));
      setAcikKosu(ayrinti(kimlik, yanit));
    } catch (error) {
      setHata(errorMessage(error));
    }
  };

  if (!liste.tanimlar.length && !liste.kosular.length && !liste.ekipler.length && !hata) return null;
  return <section aria-label="Ekipler ve iş akışları" className="orch-panel">
    {liste.ekipler.length > 0 && <>
      <p className="orch-board__eyebrow">Ekipler</p>
      <ul aria-label="Ekipler" className="orch-panel__list">
        {liste.ekipler.map((ekip) => <li className="orch-panel__row" key={ekip.ad}>
          <span><strong>{ekip.ad}</strong> <small>{ekip.tamam}/{ekip.gorev} görev{ekip.hedef ? ` · ${ekip.hedef}` : ""}</small></span>
          <span className="orch-panel__actions">
            {onCommand && <button className="orch-panel__button" onClick={() => onCommand(`/team goster ${ekip.ad}`)} type="button">Pano</button>}
            {silinecek === ekip.ad
              ? <>
                <small>Pano ve gelen kutuları silinsin mi?</small>
                <button className="orch-panel__button orch-panel__button--danger" onClick={() => void sil(ekip.ad)} type="button">Evet, sil</button>
                <button className="orch-panel__button" onClick={() => setSilinecek(null)} type="button">Vazgeç</button>
              </>
              : <button aria-label={`${ekip.ad} ekibini sil`} className="orch-panel__button" onClick={() => setSilinecek(ekip.ad)} type="button">Sil</button>}
          </span>
        </li>)}
      </ul>
    </>}
    {(liste.tanimlar.length > 0 || liste.kosular.length > 0) && <p className="orch-board__eyebrow">İş akışları</p>}
    {hata && <p className="orch-board__message" role="alert">{hata}</p>}
    {liste.tanimlar.length > 0 && <ul className="orch-panel__list">
      {liste.tanimlar.map((tanim) => <li className="orch-panel__row" key={tanim.ad}>
        <span><strong>{tanim.ad}</strong>{tanim.aciklama && <small> {tanim.aciklama}</small>}</span>
        {onCommand && <button className="orch-panel__button" onClick={() => onCommand(`/workflows ${tanim.ad}`)} type="button">Çalıştır</button>}
      </li>)}
    </ul>}
    {liste.kosular.length > 0 && <ul aria-label="Son koşular" className="orch-panel__list">
      {liste.kosular.slice(0, 8).map((kosu) => {
        const biten = kosu.nodes.filter((dugum) => dugum.status === "tamam").length;
        return <li className="orch-panel__row" key={kosu.run_id}>
          <span><strong>{kosu.name}</strong> <small>{DURUM[kosu.status] ?? kosu.status} · {biten}/{kosu.nodes.length} adım · {kosu.agents_started} ajan</small></span>
          <span className="orch-panel__actions">
            <button aria-expanded={acikKosu?.kimlik === kosu.run_id} aria-label={`${kosu.name} koşusunun ayrıntısı`} className="orch-panel__button" onClick={() => void ayrintiAc(kosu.run_id)} type="button">Ayrıntı</button>
            {kosu.status === "calisiyor" && <button className="orch-panel__button" onClick={() => void iptal(kosu.run_id)} type="button">Durdur</button>}
          </span>
          {acikKosu?.kimlik === kosu.run_id && <div className="orch-panel__detail">
            <ul className="orch-board__nodes">
              {acikKosu.dugumler.map((dugum) => <li className="orch-node" data-durum={dugum.durum} key={dugum.id}>
                <span aria-hidden="true" className="orch-node__dot" />
                <span className="orch-node__label">{dugum.etiket}</span>
                <span className="orch-node__state">{DUGUM_DURUMU[dugum.durum] ?? dugum.durum}</span>
                {dugum.ozet && dugum.durum !== "tamam" && <span className="orch-node__note">{dugum.ozet}</span>}
              </li>)}
            </ul>
            {acikKosu.rapor && <pre className="orch-panel__report">{acikKosu.rapor}</pre>}
          </div>}
        </li>;
      })}
    </ul>}
  </section>;
}
