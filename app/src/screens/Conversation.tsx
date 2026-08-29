import { Button } from "../ui/Button";
import "./Conversation.css";

export interface Mesaj {
  metin: string;
  rol: "kullanici" | "asistan" | "olay";
}

function AssistantMessage({ text }: { text: string }) {
  const copy = () => {
    void navigator.clipboard?.writeText(text);
  };
  return (
    <article aria-label="Fusion yanıtı" className="conversation__article">
      <div className="conversation__text">{text}</div>
      <div className="conversation__actions">
        <Button aria-label="Yanıtı kopyala" icon="copy" iconOnly onClick={copy} />
      </div>
    </article>
  );
}

export function Conversation({ mesajlar }: { mesajlar: Mesaj[] }) {
  return (
    <div className="conversation">
      <div aria-live="polite" className="conversation__stream">
        {mesajlar.map((message, index) => {
          if (message.rol === "kullanici") {
            return (
              <div className="conversation__message conversation__message--user" key={index}>
                <div className="conversation__bubble">{message.metin}</div>
              </div>
            );
          }
          if (message.rol === "olay") {
            return (
              <div className="conversation__message conversation__message--event" key={index}>
                <details className="conversation__event">
                  <summary>{message.metin}</summary>
                  <div className="conversation__event-detail">Çalışma ayrıntısı</div>
                </details>
              </div>
            );
          }
          return (
            <div className="conversation__message conversation__message--assistant" key={index}>
              <AssistantMessage text={message.metin} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
