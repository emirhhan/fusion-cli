import { useEffect, useRef, useState } from "react";
import { sureMetni } from "../protocol/adimOzeti";
import { ToolTrail, useElapsedSeconds } from "../screens/ActivityLine";
import { AgentAvatar, ajanRengi } from "./AgentAvatar";
import type { AjanKarti } from "./ekipOlaylari";
import "./TeamCards.css";

/**
 * Alt ajan kartları — her ekip üyesi kendi kartında çalışır (Codex'teki gibi).
 *
 * Kart üç katmanlıdır: kimlik (avatar + ünvan), iş (görev metni) ve durum
 * (çalışırken canlı adım + süre, bitince tek satırlık sonuç). Adımların tamamı
 * akışı kaplamaz; "adımlar" açılınca görünür. Paralel başlayan ajanlar aynı
 * grupta yan yana durur, dar ekranda alt alta iner.
 */

/** İptal kabul edildi ama ajan bitiş olayı gelmezse düğmenin yeniden denemeye açılma süresi. */
export const CANCEL_RETRY_MS = 8_000;

const DURUM_METNI: Record<AjanKarti["durum"], string> = {
  calisiyor: "çalışıyor",
  bitti: "bitti",
  yarim: "yarım kaldı",
  iptal: "iptal edildi",
  butce: "sınıra ulaştı",
};

function canliSatir(kart: AjanKarti): string {
  const son = kart.adimlar[kart.adimlar.length - 1];
  if (!son) return "Başlıyor";
  return son.ayrinti && son.basladi ? `${son.metin} · ${son.ayrinti}` : son.metin;
}

function AgentCard({ kart, canli, onCancel, cocuklar }: { kart: AjanKarti; canli: boolean; onCancel?: (id: string) => Promise<void>; cocuklar?: Map<string, AjanKarti[]> }) {
  const pending = useRef(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const cancel = () => {
    if (!onCancel || pending.current) return;
    pending.current = true;
    setCancelling(true);
    setError("");
    void Promise.resolve().then(() => onCancel(kart.id)).catch(() => {
      pending.current = false;
      setCancelling(false);
      setError("Ajan durdurulamadı. Yeniden deneyebilirsin.");
    });
  };
  const calisiyor = kart.durum === "calisiyor" && canli;
  useEffect(() => {
    if (!cancelling) return;
    const timer = window.setTimeout(() => {
      pending.current = false;
      setCancelling(false);
      setError("Ajan hâlâ çalışıyor. Yeniden durdurmayı deneyebilirsin.");
    }, CANCEL_RETRY_MS);
    return () => window.clearTimeout(timer);
  }, [cancelling]);
  // Tur bitti ama ajan bitiş olayı gelmedi (iptal, kopan bağlantı): yarım sayılır.
  const durum: AjanKarti["durum"] = calisiyor
    ? "calisiyor"
    : kart.durum === "calisiyor" ? "yarim" : kart.durum;
  const saniye = useElapsedSeconds(calisiyor, kart.baslangic);
  const izler = kart.adimlar.filter((adim) => adim.arac || adim.kalici);
  const sure = calisiyor ? saniye : kart.sureSn;
  const altAjanlar = cocuklar?.get(kart.id) ?? [];
  return (
    <article
      aria-label={`${kart.unvan}: ${kart.gorev}`}
      className="agent-card"
      data-renk={ajanRengi(kart.renk)}
      data-state={durum}
      data-depth={kart.derinlik ?? 1}
    >
      <header className="agent-card__head">
        <AgentAvatar ad={kart.unvan} avatar={kart.avatar} calisiyor={calisiyor} renk={kart.renk} />
        <div className="agent-card__who">
          <span className="agent-card__title">{kart.unvan}</span>
          <span className="agent-card__state">
            {DURUM_METNI[durum]}
            {sure ? ` · ${sureMetni(Math.round(sure))}` : ""}
          </span>
        </div>
      </header>
      {calisiyor && onCancel && <button type="button" disabled={cancelling} onClick={cancel}>{cancelling ? "Durduruluyor…" : "Ajanı durdur"}</button>}
      {error && <p role="alert">{error}</p>}
      <p className="agent-card__task" title={kart.gorev}>{kart.gorev}</p>
      {calisiyor ? (
        <p className="agent-card__now">
          <span aria-hidden="true" className="agent-card__dot" />
          <span className="agent-card__now-text">{canliSatir(kart)}</span>
        </p>
      ) : (
        kart.ozet && <p className="agent-card__result">{kart.ozet}</p>
      )}
      {kart.degisenYollar && kart.degisenYollar.length > 0 && <p className="agent-card__result">Değişen dosyalar: {kart.degisenYollar.join(", ")}</p>}
      {izler.length > 0 && (
        <details className="agent-card__steps">
          <summary>{izler.length} adım</summary>
          <ToolTrail adimlar={izler} />
        </details>
      )}
      {altAjanlar.length > 0 && (
        <div aria-label={`${kart.unvan} alt ajanları`} className="agent-card__children" role="group">
          {altAjanlar.map((cocuk) => <AgentCard canli={canli} cocuklar={cocuklar} kart={cocuk} key={cocuk.id} onCancel={onCancel} />)}
        </div>
      )}
    </article>
  );
}

/**
 * Ağaç: `ust` alanı listede bulunan bir karta işaret ediyorsa o kart üstünün altında
 * çizilir (P-035). Üstü listede olmayan kart kök sayılır; hiçbir kart kaybolmaz.
 */
export function ajanAgaci(ajanlar: AjanKarti[]): { kokler: AjanKarti[]; cocuklar: Map<string, AjanKarti[]> } {
  const kimlikler = new Set(ajanlar.map((kart) => kart.id));
  const cocuklar = new Map<string, AjanKarti[]>();
  const kokler: AjanKarti[] = [];
  for (const kart of ajanlar) {
    if (kart.ust && kimlikler.has(kart.ust) && kart.ust !== kart.id) {
      cocuklar.set(kart.ust, [...(cocuklar.get(kart.ust) ?? []), kart]);
    } else {
      kokler.push(kart);
    }
  }
  return { kokler, cocuklar };
}

export interface TeamCardsProps {
  ajanlar: AjanKarti[];
  /** Tur hâlâ sürüyor mu? Tur bittiyse "çalışıyor" kalan kart yarım sayılır. */
  canli: boolean;
  onCancel?: (id: string) => Promise<void>;
}

export function TeamCards({ ajanlar, canli, onCancel }: TeamCardsProps) {
  if (ajanlar.length === 0) return null;
  const { kokler, cocuklar } = ajanAgaci(ajanlar);
  const etiket = kokler.length > 1 ? `${kokler.length} ajan aynı anda çalışıyor` : "Alt ajan";
  return (
    <section aria-label={etiket} className="team-cards" data-count={kokler.length}>
      {kokler.length > 1 && <h3 className="team-cards__label">{etiket}</h3>}
      <div className="team-cards__grid">
        {kokler.map((kart) => <AgentCard canli={canli} cocuklar={cocuklar} kart={kart} key={kart.id} onCancel={onCancel} />)}
      </div>
    </section>
  );
}
