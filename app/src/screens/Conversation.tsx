import { Button } from "../ui/Button";
import "./Conversation.css";

import type { OlayAdimi } from "../protocol/olayMetni";

export interface Mesaj {
  metin: string;
  rol: "kullanici" | "asistan" | "olay";
  /** Yalnız `rol === "olay"` için: blokta toplanan adımlar. */
  adimlar?: OlayAdimi[];
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

/**
 * Çalışma bloğu.
 *
 * Ardışık adımlar TEK bir satırda toplanır: eskiden her model çağrısı ayrı bir
 * "model düşünüyor…" satırı açıyordu ve aynı cümle üst üste iki kez
 * görünüyordu. Başlıkta yalnız en son yapılan iş yazar; açınca hangi model,
 * hangi dosya ve hangi adres olduğu görünür.
 */
function ActivityBlock({ adimlar, metin }: { adimlar: OlayAdimi[]; metin: string }) {
  const sonuncu = adimlar[adimlar.length - 1];
  const baslik = sonuncu?.metin ?? metin;
  const sayi = adimlar.length;
  // Tek adımlı ve ayrıntısız blokta açılır kapanır bir kutu boş yere yer kaplar
  // ve aynı cümleyi iki kez gösterirdi; düz satır yeterli.
  if (sayi <= 1 && !sonuncu?.ayrinti && !sonuncu?.kaynak) {
    return <span className="conversation__event-title">{baslik}</span>;
  }
  return (
    <details className="conversation__event">
      <summary>
        <span className="conversation__event-title">{baslik}</span>
        {sayi > 1 && <span className="conversation__event-count">{sayi} adım</span>}
      </summary>
      <ol className="conversation__event-steps">
        {adimlar.map((adim, index) => (
          <li key={index}>
            <span className="conversation__step-title">{adim.metin}</span>
            {adim.kaynak ? (
              <a
                className="conversation__step-source"
                href={adim.kaynak}
                rel="noreferrer noopener"
                target="_blank"
              >
                {adim.kaynak}
              </a>
            ) : (
              adim.ayrinti && <span className="conversation__step-detail">{adim.ayrinti}</span>
            )}
          </li>
        ))}
      </ol>
    </details>
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
                <ActivityBlock adimlar={message.adimlar ?? []} metin={message.metin} />
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
