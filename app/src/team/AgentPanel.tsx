import type { Mesaj } from "../screens/Conversation";
import type { AjanKarti } from "./ekipOlaylari";
import { useState } from "react";
import { TeamCards, type TeamCardsProps } from "./TeamCards";
import "./AgentPanel.css";
/** Aynı oturumun olaylarıyla güncellenen ajan listesi ve seçili canlı iz. */
export function AgentPanel({ ajanlar, canli, onCancel }: TeamCardsProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = ajanlar.find((agent) => agent.id === selectedId);
  if (!ajanlar.length) return <p className="agent-panel__empty">Henüz alt ajan çalıştırılmadı. Başlayan ajanlar ve canlı adımları burada görünür.</p>;
  return <div className="agent-panel">
    <div aria-label="Alt ajanlar" className="agent-panel__list">
      {ajanlar.map((agent) => <button aria-pressed={agent.id === selected?.id} className="agent-panel__item" key={agent.id} onClick={() => setSelectedId(agent.id)} type="button">
        <strong>{agent.unvan}</strong><span>{agent.gorev}</span>
        <small>{agent.durum === "calisiyor" ? canli ? "Çalışıyor" : "Yarım kaldı" : agent.durum === "bitti" ? "Tamamlandı" : agent.durum === "iptal" ? "İptal edildi" : agent.durum === "butce" ? "Sınıra ulaştı" : "Yarım kaldı"}</small>
      </button>)}
    </div>
    {selected ? <TeamCards ajanlar={[selected]} canli={canli} onCancel={onCancel} /> : <p className="agent-panel__empty">Canlı adımlarını görmek için bir ajan seç.</p>}
  </div>;
}

/** Ajan seçimi mesaj verisini değiştirmez; tur sınırı oturum deposunca yönetilir. */
export function agentCardsForMessages(messages: Mesaj[]): AjanKarti[] {
  return messages.flatMap((message) => message.rol === "ekip" ? message.ajanlar ?? [] : []);
}
