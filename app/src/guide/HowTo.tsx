import { useMemo, useState } from "react";
import { Button } from "../ui/Button";
import { GUIDE_GROUPS, GUIDE_TOPICS, type GuideGroup, type GuideSettingsSection, type GuideTopic } from "./topics";
import "./guide.css";

interface HowToProps {
  onOpenSettings?: (section: GuideSettingsSection) => void;
}

/**
 * Ayarlar → Nasıl yapılır: görev başlıklarıyla kısa tarifler.
 *
 * Eskiden her konu büyük bir ekran görüntüsüyle alt alta akıyordu; görüntüler eski sürümden
 * kalmıştı ve sayfa 6000 px'i aşıyordu. Artık her görev tek satırlık bir başlıktır; açınca
 * nerede olduğu ve 2-4 adım görünür. Görseller yalnız kurulumdaki eğitimde (GuideTour) durur.
 */
export function HowTo({ onOpenSettings }: HowToProps) {
  const [query, setQuery] = useState("");
  const text = query.trim().toLocaleLowerCase("tr");
  const topics = useMemo(() => GUIDE_TOPICS.filter((topic) => !text
    || `${topic.title} ${topic.summary} ${topic.where} ${topic.steps.join(" ")}`.toLocaleLowerCase("tr").includes(text)), [text]);

  return (
    <div className="guide-howto" id="settings-howto">
      <p className="settings__hint">
        Fusion'da bir işi nasıl yapacağının kısa tarifi. Bir başlığa tıkla: nerede olduğu ve adımlar açılır.
      </p>
      <input aria-label="Konularda ara" className="settings__search guide-howto__search" onChange={(event) => setQuery(event.target.value)} placeholder="Konularda ara" type="search" value={query} />
      {topics.length === 0 && <p className="settings__hint" role="status">Bu aramayla eşleşen konu yok.</p>}
      {(Object.keys(GUIDE_GROUPS) as GuideGroup[]).map((group) => {
        const rows = topics.filter((topic) => topic.group === group);
        if (rows.length === 0) return null;
        return (
          <section aria-labelledby={`guide-group-${group}`} className="guide-howto__group" key={group}>
            <h4 id={`guide-group-${group}`}>{GUIDE_GROUPS[group]}</h4>
            <div className="guide-howto__list">
              {rows.map((topic) => <HowToItem key={topic.id} onOpenSettings={onOpenSettings} open={text.length > 0} topic={topic} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/** Tek görev: başlık + özet; açılınca "Nerede" ve numaralı adımlar. Arama sırasında açık gelir. */
function HowToItem({ topic, open, onOpenSettings }: { topic: GuideTopic; open: boolean; onOpenSettings?: (section: GuideSettingsSection) => void }) {
  return (
    <details className="guide-howto__item" id={`guide-${topic.id}`} open={open || undefined}>
      <summary>
        <span className="guide-howto__title">{topic.title}</span>
        <span className="guide-howto__summary">{topic.summary}</span>
      </summary>
      <div className="guide-howto__body">
        <p className="guide-howto__where"><strong>Nerede:</strong> {topic.where}</p>
        <ol className="guide-howto__steps">
          {topic.steps.map((step) => <li key={step}>{step}</li>)}
        </ol>
        {topic.settingsSection && onOpenSettings && (
          <div>
            <Button onClick={() => onOpenSettings(topic.settingsSection!)} variant="secondary">Ayarlar'da aç</Button>
          </div>
        )}
      </div>
    </details>
  );
}
