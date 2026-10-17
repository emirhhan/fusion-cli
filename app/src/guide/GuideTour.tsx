import { useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
import { DevToolsCheck } from "./DevToolsCheck";
import { markSeen, pendingIds, readSeen } from "./progress";
import { TopicCard } from "./TopicCard";
import { ONBOARDING_TOPICS } from "./topics";
import "./guide.css";

/**
 * Kurulumdaki "Eğitim" adımı: konular tek tek, gerçek ekran görüntüsüyle.
 * Atlanan konu kaybolmaz; hepsi Ayarlar → Nasıl yapılır'da "Bakılmadı" etiketiyle durur.
 */
export function GuideTour({ client }: { client: ProtocolClient }) {
  const [seen, setSeen] = useState<ReadonlySet<string>>(readSeen);
  const [index, setIndex] = useState(0);
  const topic = ONBOARDING_TOPICS[index];
  const pending = pendingIds(ONBOARDING_TOPICS.map((item) => item.id), seen).length;
  const last = index === ONBOARDING_TOPICS.length - 1;
  const advance = (offset: -1 | 1) => {
    if (offset === 1) setSeen(markSeen(topic.id));
    setIndex((current) => Math.min(Math.max(current + offset, 0), ONBOARDING_TOPICS.length - 1));
  };

  return (
    <div className="guide-tour">
      <p className="onboarding__eyebrow">Nasıl kullanılır</p>
      <h1>Fusion'ı tanıyın</h1>
      <p className="onboarding__lead">
        Her özelliğin nerede olduğunu ve nasıl yapıldığını adım adım görün. İstemezseniz atlayın: hepsi Ayarlar → Nasıl yapılır sayfasında kalır.
      </p>
      <DevToolsCheck client={client} />
      <nav aria-label="Eğitim konuları" className="guide-tour__tabs">
        {ONBOARDING_TOPICS.map((item, position) => (
          <button
            aria-current={position === index ? "step" : undefined}
            data-seen={seen.has(item.id)}
            key={item.id}
            onClick={() => setIndex(position)}
            type="button"
          >{item.title}</button>
        ))}
      </nav>
      <TopicCard onMarkSeen={(id) => setSeen(markSeen(id))} seen={seen.has(topic.id)} size="large" topic={topic} />
      <div className="guide-tour__pager">
        <Button disabled={index === 0} onClick={() => advance(-1)} variant="ghost">Önceki konu</Button>
        <span role="status">{index + 1} / {ONBOARDING_TOPICS.length}{pending > 0 ? ` · ${pending} konu bakılmadı` : " · hepsine baktınız"}</span>
        <Button disabled={last} onClick={() => advance(1)} variant="secondary">Sonraki konu</Button>
      </div>
    </div>
  );
}
