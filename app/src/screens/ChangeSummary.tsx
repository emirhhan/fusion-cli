import { useState } from "react";
import { countChanges, DiffCard, parseDiff } from "../markdown/DiffCard";
import { Icon } from "../ui/Icon";
import type { Mesaj } from "./Conversation";
import "./ChangeSummary.css";

export interface FileChange {
  path: string;
  added: number;
  removed: number;
  patches: string[];
}

/** Yalnız başarılı ve gerçek diff taşıyan adımları kendi kullanıcı turuna bağla. */
export function turnChanges(messages: Mesaj[], running: boolean): Map<number, FileChange[]> {
  const summaries = new Map<number, FileChange[]>();
  let files = new Map<string, FileChange>();
  let finalIndex = -1;
  let changeIndex = -1;
  const finish = (end: number) => {
    const anchor = Math.max(finalIndex, changeIndex);
    if (files.size && anchor >= 0 && !(running && end === messages.length)) {
      summaries.set(anchor, [...files.values()]);
    }
    files = new Map(); finalIndex = -1; changeIndex = -1;
  };
  const record = (path: string | undefined, diff: string | undefined, index: number) => {
    if (!path || !diff?.trim()) return;
    const counts = countChanges(parseDiff(diff));
    const previous = files.get(path);
    files.set(path, {
      path, added: (previous?.added ?? 0) + counts.added,
      removed: (previous?.removed ?? 0) + counts.removed,
      patches: [...(previous?.patches ?? []), diff],
    });
    changeIndex = index;
  };
  messages.forEach((message, index) => {
    if (message.rol === "kullanici") { finish(index); return; }
    if (message.rol === "asistan" && !message.ara && !message.akan) finalIndex = index;
    if (message.rol === "olay") {
      for (const step of message.adimlar ?? []) {
        if (step.durum === "ok" && !step.basladi) record(step.yol, step.diff, index);
      }
    } else if (message.rol === "degisiklik") record(message.metin, message.diff, index);
    else if (message.rol === "ekip") {
      for (const agent of message.ajanlar ?? []) for (const step of agent.adimlar) {
        if (step.durum === "ok" && !step.basladi) record(step.yol, step.diff, index);
      }
    }
  });
  finish(messages.length);
  return summaries;
}

/** Satır sayıları gözlenen gerçek düzenlemelerdir; aynı yol tek kez listelenir. */
export function ChangeSummary({ files, onOpenFile }: {
  files: FileChange[];
  onOpenFile?: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? files : files.slice(0, 3);
  const added = files.reduce((sum, file) => sum + file.added, 0);
  const removed = files.reduce((sum, file) => sum + file.removed, 0);
  return <section aria-label="Dosya değişiklikleri" className="change-summary">
    <header className="change-summary__header">
      <span className="change-summary__icon"><Icon name="files" /></span>
      <div className="change-summary__heading">
        <strong>{files.length} dosya düzenlendi</strong>
        <span className="change-summary__counts" title="Bu turda gözlenen eklenen ve silinen satırlar">
          <span className="change-summary__added">+{added}</span>
          <span className="change-summary__removed">−{removed}</span>
        </span>
      </div>
      <button type="button" className="change-summary__view" aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}>Değişiklikleri görüntüle</button>
    </header>
    <ul className="change-summary__files">
      {shown.map((file) => <li key={file.path}>
        {onOpenFile
          ? <button type="button" className="change-summary__path" title={file.path}
              aria-label={`${file.path} dosyasını aç`} onClick={() => onOpenFile(file.path)}>{file.path}</button>
          : <span className="change-summary__path" title={file.path}>{file.path}</span>}
        <span className="change-summary__counts">
          <span className="change-summary__added">+{file.added}</span>
          <span className="change-summary__removed">−{file.removed}</span>
        </span>
      </li>)}
    </ul>
    {files.length > 3 && <button type="button" className="change-summary__more" aria-expanded={showAll}
      onClick={() => setShowAll(!showAll)}>{showAll ? "Daha az göster" : `${files.length - 3} dosya daha göster`}<Icon name="chevron" /></button>}
    {expanded && <div className="change-summary__diffs">
      {files.map((file) => <div key={file.path}>{file.patches.map((patch, index) =>
        <DiffCard key={index} path={file.path} diff={patch} onOpenFile={onOpenFile} initialExpanded />)}</div>)}
    </div>}
  </section>;
}
