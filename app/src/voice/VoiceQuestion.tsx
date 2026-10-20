import { useId, useRef, useState } from "react";
import type { VoiceAsk } from "./bridge";
interface VoiceQuestionProps { ask: VoiceAsk; onAnswer: (answer: string) => void; answerPending?: boolean; onExpand?: () => void; }
/** Özeti açmak bir karar değildir; tam soru okunmadan karar düğmesi çizilmez. */
export function VoiceQuestion({ ask, onAnswer, answerPending = false, onExpand }: VoiceQuestionProps) {
  const [expanded, setExpanded] = useState(false);
  const summary = useRef<HTMLButtonElement>(null);
  const detailId = useId();
  const paragraph = ask.metin.trim().split(/\n\s*\n/)[0].replace(/\s+/g, " ");
  return <div aria-label="Onay" className="voice-ask" role="group" onKeyDown={(event) => {
    if (event.key === "Escape" && expanded) { event.preventDefault(); event.stopPropagation(); setExpanded(false); summary.current?.focus(); }
  }}>
    <button aria-controls={expanded ? detailId : undefined} aria-expanded={expanded} aria-label={expanded ? "Soru ayrıntısını kapat" : "Sorunun tamamını oku"} className="voice-ask__summary" ref={summary} type="button" onClick={() => {
      setExpanded(!expanded); if (!expanded) onExpand?.();
    }}><span className="voice-ask__text">{paragraph || "Bir kararın bekleniyor."}</span><small>{expanded ? "Ayrıntıyı kapat" : "Tamamını oku"}</small></button>
    {expanded && <div className="voice-ask__details" id={detailId}>
      <p className="voice-ask__full">{ask.metin}</p>
      <div className="voice-ask__buttons">{ask.secenekler.map((option) => <button disabled={answerPending} key={option.deger} onClick={() => onAnswer(option.deger)} type="button">{option.etiket}</button>)}</div>
    </div>}
  </div>;
}
