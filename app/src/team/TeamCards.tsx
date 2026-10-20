import { useRef, useState } from "react";
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

function AgentCard({ kart, canli, onCancel }: { kart: AjanKarti; canli: boolean; onCancel?: (id: string) => Promise<void> }) {
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
  // Tur bitti ama ajan bitiş olayı gelmedi (iptal, kopan bağlantı): yarım sayılır.
  const durum: AjanKarti["durum"] = calisiyor
    ? "calisiyor"
    : kart.durum === "calisiyor" ? "yarim" : kart.durum;
  const saniye = useElapsedSeconds(calisiyor, kart.baslangic);
  const izler = kart.adimlar.filter((adim) => adim.arac || adim.kalici);
  const sure = calisiyor ? saniye : kart.sureSn;
  return (
    <article
      aria-label={`${kart.unvan}: ${kart.gorev}`}
      className="agent-card"
      data-renk={ajanRengi(kart.renk)}
      data-state={durum}
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
    </article>
  );
}

export interface TeamCardsProps {
  ajanlar: AjanKarti[];
  /** Tur hâlâ sürüyor mu? Tur bittiyse "çalışıyor" kalan kart yarım sayılır. */
  canli: boolean;
  onCancel?: (id: string) => Promise<void>;
}

export function TeamCards({ ajanlar, canli, onCancel }: TeamCardsProps) {
  if (ajanlar.length === 0) return null;
  const etiket = ajanlar.length > 1 ? `${ajanlar.length} ajan aynı anda çalışıyor` : "Alt ajan";
  return (
    <section aria-label={etiket} className="team-cards" data-count={ajanlar.length}>
      {ajanlar.length > 1 && <h3 className="team-cards__label">{etiket}</h3>}
      <div className="team-cards__grid">
        {ajanlar.map((kart) => <AgentCard canli={canli} kart={kart} key={kart.id} onCancel={onCancel} />)}
      </div>
    </section>
  );
}
