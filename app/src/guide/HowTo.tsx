import { useMemo, useState } from "react";
import { markSeen, pendingIds, readSeen } from "./progress";
import { TopicCard } from "./TopicCard";
import { GUIDE_GROUPS, GUIDE_TOPICS, type GuideGroup, type GuideSettingsSection } from "./topics";
import "./guide.css";

/** Ayarlar → Nasıl yapılır: bütün konular, gerçek ekran görüntüleriyle. */
export function HowTo({ onOpenSettings }: { onOpenSettings?: (section: GuideSettingsSection) => void }) {
  const [seen, setSeen] = useState<ReadonlySet<string>>(readSeen);
  const [query, setQuery] = useState("");
  const text = query.trim().toLocaleLowerCase("tr");
  const topics = useMemo(() => GUIDE_TOPICS.filter((topic) => !text
    || `${topic.title} ${topic.summary} ${topic.where} ${topic.steps.join(" ")}`.toLocaleLowerCase("tr").includes(text)), [text]);
  const pending = pendingIds(GUIDE_TOPICS.map((topic) => topic.id), seen).length;

  return (
    <div className="guide-howto" id="settings-howto">
      <p className="settings__hint">
        Fusion'daki her özelliğin nerede olduğu ve nasıl yapıldığı. Görseller uygulamanın kendi ekranlarıdır.
        {pending > 0 ? ` ${pending} konuya henüz bakılmadı.` : " Bütün konulara baktınız."}
      </p>
      <input aria-label="Konularda ara" className="settings__search" onChange={(event) => setQuery(event.target.value)} placeholder="Konularda ara" type="search" value={query} />
      {topics.length === 0 && <p role="status">Bu aramayla eşleşen konu yok.</p>}
      {(Object.keys(GUIDE_GROUPS) as GuideGroup[]).map((group) => {
        const rows = topics.filter((topic) => topic.group === group);
        if (rows.length === 0) return null;
        return (
          <section aria-label={GUIDE_GROUPS[group]} className="guide-howto__group" key={group}>
            <h4>{GUIDE_GROUPS[group]}</h4>
            {rows.map((topic) => (
              <TopicCard key={topic.id} onMarkSeen={(id) => setSeen(markSeen(id))} onOpenSettings={onOpenSettings} seen={seen.has(topic.id)} topic={topic} />
            ))}
          </section>
        );
      })}
    </div>
  );
}
