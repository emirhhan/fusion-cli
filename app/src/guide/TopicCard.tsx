import { Button } from "../ui/Button";
import { guideImageUrl, type GuideSettingsSection, type GuideTopic } from "./topics";

interface TopicCardProps {
  topic: GuideTopic;
  seen: boolean;
  /** Küçük görsel: Ayarlar sayfasında liste, kurulumda büyük. */
  size?: "compact" | "large";
  onOpenSettings?: (section: GuideSettingsSection) => void;
  onMarkSeen?: (id: string) => void;
}

/** Tek bir konu: nerede olduğu, gerçek ekran görüntüsü, numaralı adımlar. */
export function TopicCard({ topic, seen, size = "compact", onOpenSettings, onMarkSeen }: TopicCardProps) {
  return (
    <article className="guide-topic" data-seen={seen} data-size={size} id={`guide-${topic.id}`}>
      <header className="guide-topic__head">
        <h3>{topic.title}</h3>
        {!seen && <span className="guide-topic__badge">Bakılmadı</span>}
      </header>
      <p className="guide-topic__summary">{topic.summary}</p>
      <p className="guide-topic__where"><strong>Nerede:</strong> {topic.where}</p>
      <figure className="guide-topic__figure">
        <img alt={topic.imageAlt} decoding="async" height={600} loading="lazy" src={guideImageUrl(topic)} width={960} />
      </figure>
      <ol className="guide-topic__steps">
        {topic.steps.map((step) => <li key={step}>{step}</li>)}
      </ol>
      <div className="guide-topic__actions">
        {topic.settingsSection && onOpenSettings && (
          <Button onClick={() => onOpenSettings(topic.settingsSection!)} variant="secondary">Ayarlar'da aç</Button>
        )}
        {onMarkSeen && !seen && <Button onClick={() => onMarkSeen(topic.id)} variant="ghost">Gördüm</Button>}
      </div>
    </article>
  );
}
