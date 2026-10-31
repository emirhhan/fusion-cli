import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import "./OrchestrationBoard.css";

/**
 * Ajanlar sekmesindeki "İş akışları" bölümü (P-062) — `/workflows`'un masaüstü yüzü.
 *
 * Kayıtlı tanımlar `/workflows <ad>` komutuyla ajana verilir (terminaldeki aynı yol);
 * koşan koşu `akis.iptal` ile durdurulur. Liste, pano olayı geldikçe yeniden okunur.
 */

interface Tanim { ad: string; kapsam: string; aciklama: string }
interface Kosu {
  run_id: string;
  name: string;
  status: string;
  agents_started: number;
  nodes: { status: string }[];
  phase: string;
  message: string;
}

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

function kosular(yanit: Record<string, unknown>): Kosu[] {
  const ham = Array.isArray(yanit.kosular) ? yanit.kosular : [];
  return ham.filter((item): item is Kosu => !!item && typeof item === "object" && typeof (item as Kosu).run_id === "string");
}

export function OrchestrationPanel({ client, onCommand }: { client: ProtocolClient; onCommand?: (line: string) => void }) {
  const [liste, setListe] = useState<{ tanimlar: Tanim[]; kosular: Kosu[] }>({ tanimlar: [], kosular: [] });
  const [hata, setHata] = useState<string | null>(null);
  /** Görülen koşu/ekip durumları: liste yalnız durum DEĞİŞİNCE yeniden okunur (her düğümde değil). */
  const gorulen = useRef(new Map<string, string>());

  const yukle = useCallback(async () => {
    try {
      const yanit = await client.request("akis.liste", {});
      if (yanit.ok !== true) throw new Error(String(yanit.metin ?? "İş akışları okunamadı."));
      setListe({ tanimlar: tanimlar(yanit), kosular: kosular(yanit) });
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

  if (!liste.tanimlar.length && !liste.kosular.length && !hata) return null;
  return <section aria-label="İş akışları" className="orch-panel">
    <p className="orch-board__eyebrow">İş akışları</p>
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
          {kosu.status === "calisiyor" && <button className="orch-panel__button" onClick={() => void iptal(kosu.run_id)} type="button">Durdur</button>}
        </li>;
      })}
    </ul>}
  </section>;
}
