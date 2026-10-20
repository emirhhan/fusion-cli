import { useState } from "react";
import { countChanges, DiffCard, parseDiff } from "../markdown/DiffCard";
import { Icon } from "../ui/Icon";
import type { Mesaj } from "./Conversation";
import "./ChangeSummary.css";

export type ChangeKind = "created" | "edited" | "deleted";

export interface FileChange {
  path: string;
  kind: ChangeKind;
  added: number;
  removed: number;
  patches: string[];
}

/** Unified diff'in hunk başlığından işlem tipi: `-0,0` yeni dosya, `+0,0` silinen dosya. */
export function changeKind(diff: string): ChangeKind {
  if (/^@@ -0,0 \+/m.test(diff)) return "created";
  if (/^@@ -\d+(?:,\d+)? \+0,0 @@/m.test(diff)) return "deleted";
  return "edited";
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
      path, kind: previous ? (changeKind(diff) === "deleted" ? "deleted" : previous.kind) : changeKind(diff), added: (previous?.added ?? 0) + counts.added,
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

const KIND_ORDER: ChangeKind[] = ["created", "edited", "deleted"];
const KIND_LABEL: Record<ChangeKind, string> = {
  created: "dosya oluşturuldu", edited: "dosya düzenlendi", deleted: "dosya silindi",
};

function CountPair({ added, removed }: { added: number; removed: number }) {
  return <span className="change-summary__counts" title="Bu turda gözlenen eklenen ve silinen satırlar">
    <span className="change-summary__added">+{added}</span>
    <span className="change-summary__removed">−{removed}</span>
  </span>;
}

function ChangeGroup({ kind, files, onOpenFile }: {
  kind: ChangeKind; files: FileChange[]; onOpenFile?: (path: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [diffOpen, setDiffOpen] = useState<string | null>(null);
  const added = files.reduce((sum, file) => sum + file.added, 0);
  const removed = files.reduce((sum, file) => sum + file.removed, 0);
  return <div className="change-summary__group" data-kind={kind}>
    <button type="button" className="change-summary__head" aria-expanded={open} onClick={() => setOpen(!open)}>
      <Icon name="chevron" />
      <strong>{files.length} {KIND_LABEL[kind]}</strong>
      <CountPair added={added} removed={removed} />
    </button>
    {open && <ul className="change-summary__files">
      {files.map((file) => <li key={file.path}>
        <div className="change-summary__row">
          {onOpenFile
            ? <button type="button" className="change-summary__path" title={file.path}
                aria-label={`${file.path} dosyasını aç`} onClick={() => onOpenFile(file.path)}>{file.path}</button>
            : <span className="change-summary__path" title={file.path}>{file.path}</span>}
          <CountPair added={file.added} removed={file.removed} />
          <button type="button" className="change-summary__view" aria-expanded={diffOpen === file.path}
            aria-label={`${file.path} farkını göster`}
            onClick={() => setDiffOpen(diffOpen === file.path ? null : file.path)}><Icon name="chevron" /></button>
        </div>
        {diffOpen === file.path && <div className="change-summary__diffs">
          {file.patches.map((patch, index) =>
            <DiffCard key={index} path={file.path} diff={patch} onOpenFile={onOpenFile} initialExpanded />)}
        </div>}
      </li>)}
    </ul>}
  </div>;
}

/** İşlem tipi başına tek satır; açılınca o tipteki dosyalar listelenir. */
export function ChangeSummary({ files, onOpenFile }: {
  files: FileChange[];
  onOpenFile?: (path: string) => void;
}) {
  return <section aria-label="Dosya değişiklikleri" className="change-summary">
    {KIND_ORDER.map((kind) => {
      const group = files.filter((file) => file.kind === kind);
      return group.length ? <ChangeGroup key={kind} kind={kind} files={group} onOpenFile={onOpenFile} /> : null;
    })}
  </section>;
}
