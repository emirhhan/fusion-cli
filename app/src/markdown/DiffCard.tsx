import { useMemo, useState } from "react";
import "./markdown.css";

/**
 * Değişiklik kartı — Fusion bir dosyayı değiştirdiğinde ne yaptığı görünsün.
 *
 * Ölçülmüş boşluk: `ToolExecuted` olayı çalıştırmadan ÖNCE üretilmiş unified
 * diff'i zaten taşıyordu ama arayüz onu atıyordu. Kullanıcı "araç çalıştı:
 * write_file" satırından başka bir şey görmüyor, dosyaya ne yazıldığını
 * anlamak için dosyayı elle açmak zorunda kalıyordu.
 *
 * Kart KALICIDIR: çalışma göstergesi iş bitince kaybolur, değişiklik kaydı
 * kalmalıdır — yapılan işin kanıtı odur.
 */

/** Kapalı kartta görünen diff satırı sayısı. */
const PREVIEW_LINES = 5;

type DiffKind = "add" | "remove" | "meta" | "hunk" | "context";

export interface DiffRow {
  kind: DiffKind;
  text: string;
}

/** Unified diff metnini satır türleriyle birlikte çöz. */
export function parseDiff(diff: string): DiffRow[] {
  return diff.split("\n").map((text) => ({ kind: rowKind(text), text }));
}

function rowKind(text: string): DiffKind {
  if (text.startsWith("+++") || text.startsWith("---")) return "meta";
  if (text.startsWith("@@")) return "hunk";
  if (text.startsWith("+")) return "add";
  if (text.startsWith("-")) return "remove";
  return "context";
}

/** Eklenen ve çıkarılan satır sayısı — başlıktaki özet. */
export function countChanges(rows: readonly DiffRow[]): { added: number; removed: number } {
  return {
    added: rows.filter((row) => row.kind === "add").length,
    removed: rows.filter((row) => row.kind === "remove").length,
  };
}

export interface DiffCardProps {
  diff: string;
  /** Değişen dosyanın yolu; başlıkta görünür ve tıklanınca açılır. */
  path: string;
  onOpenFile?: (path: string) => void;
}

export function DiffCard({ diff, path, onOpenFile }: DiffCardProps) {
  const [open, setOpen] = useState(false);
  const rows = useMemo(() => parseDiff(diff), [diff]);
  const { added, removed } = useMemo(() => countChanges(rows), [rows]);
  const collapsible = rows.length > PREVIEW_LINES;
  const shown = open || !collapsible ? rows : rows.slice(0, PREVIEW_LINES);

  return (
    <figure className="code-card diff-card" data-open={open || !collapsible}>
      <figcaption className="code-card__head">
        {onOpenFile ? (
          <button
            className="code-card__name code-card__name--link"
            onClick={() => onOpenFile(path)}
            title={`${path} dosyasını aç`}
            type="button"
          >
            {path}
          </button>
        ) : (
          <span className="code-card__name">{path}</span>
        )}
        <span className="diff-card__stat diff-card__stat--add">+{added}</span>
        <span className="diff-card__stat diff-card__stat--remove">−{removed}</span>
      </figcaption>
      <div className="code-card__body">
        <pre>
          <code>
            {shown.map((row, index) => (
              <span className="diff-card__line" data-kind={row.kind} key={index}>
                {row.text || " "}
                {"\n"}
              </span>
            ))}
          </code>
        </pre>
      </div>
      {collapsible && (
        <button
          aria-expanded={open}
          className="code-card__toggle"
          onClick={() => setOpen((current) => !current)}
          type="button"
        >
          {open ? "Gizle" : `Değişikliği göster · ${rows.length} satır`}
        </button>
      )}
    </figure>
  );
}
