import { Markdown } from "../markdown/Markdown";
import { ActivityLine, ToolTrail } from "./ActivityLine";
import type { Mesaj } from "./Conversation";

interface WorkGroup {
  end: number;
  items: Mesaj[];
}

/** Sadece ara anlatım ve araç izlerini birleştir; cevap ve hata sınırlarını koru. */
export function workGroups(messages: Mesaj[], isError: (message: Mesaj) => boolean): Map<number, WorkGroup> {
  const groups = new Map<number, WorkGroup>();
  let start = 0;
  let items: Mesaj[] = [];
  const flush = () => {
    if (items.some((item) => item.ara)) groups.set(start, { end: start + items.length, items });
    items = [];
  };
  messages.forEach((message, index) => {
    const work = (message.rol === "asistan" && message.ara && !message.akan && !isError(message))
      || (message.rol === "olay" && !message.adimlar?.some((step) => step.sonuc));
    if (!work) { flush(); return; }
    if (items.length === 0) start = index;
    items.push(message);
  });
  flush();
  return groups;
}

export function WorkHistory({ items, active, activityIndex, onOpenFile, showSteps = false }: {
  items: Mesaj[];
  active: boolean;
  activityIndex?: number;
  onOpenFile?: (path: string) => void;
  showSteps?: boolean;
}) {
  const latest = active ? [...items].reverse().find((item) => item.ara) : undefined;
  const activity = active && activityIndex !== undefined ? items[activityIndex] : undefined;
  const steps = activity?.adimlar ?? [];
  const currentStep = steps[steps.length - 1];
  const finishedSteps = (item: Mesaj) => (item.adimlar ?? []).filter((step) => (step.arac || step.kalici) && !step.basladi);
  const history = items.filter((item) => item !== latest && (
    item.ara || finishedSteps(item).length > 0
  ));
  const failed = history.some((item) => item.adimlar?.some((step) => step.durum === "failed"));
  return <div className="conversation__message conversation__work">
    {history.length > 0 && <details className="conversation__work-details" open={showSteps} data-failed={failed || undefined}>
      <summary>Çalışma ayrıntıları <span>{history.length} kayıt{failed ? " · hata var" : ""}</span></summary>
      <ol className="conversation__work-list">
        {history.map((item, index) => <li key={item.id ?? index}>
          {item.ara
            ? <Markdown text={item.metin} onOpenFile={onOpenFile} />
            : <ToolTrail adimlar={finishedSteps(item)} />}
        </li>)}
      </ol>
    </details>}
    {latest && <div className="conversation__work-current"><Markdown text={latest.metin} onOpenFile={onOpenFile} /></div>}
    {activity && <ActivityLine aktif
      adimlar={currentStep?.basladi ? [currentStep] : [{ metin: "Düşünüyor" }]}
      baslangicZamani={activity.baslangicZamani} tokenSayisi={activity.tokenSayisi} />}
  </div>;
}
