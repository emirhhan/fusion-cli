import { useState, type KeyboardEvent } from "react";

/** Claude Desktop gibi: başlık çubuğundaki sohbet adına tıklayınca yeniden adlandırılır (#443). */
interface EditableTitleProps {
  title: string;
  onRename?: (name: string) => void | Promise<void>;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function EditableTitle({ title, onRename }: EditableTitleProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!onRename) return <h1>{title}</h1>;

  const cancel = () => { setDraft(null); setError(null); };
  const commit = async () => {
    const name = (draft ?? "").trim();
    if (!name || name === title) { cancel(); return; }
    setSaving(true);
    try {
      await onRename(name);
      cancel();
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setSaving(false);
    }
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") { event.preventDefault(); void commit(); }
    if (event.key === "Escape") { event.preventDefault(); cancel(); }
  };

  if (draft === null) {
    return (
      <h1>
        <button
          aria-label={`Sohbeti yeniden adlandır: ${title}`}
          className="app-header__title-button"
          onClick={() => setDraft(title)}
          title="Yeniden adlandırmak için tıkla"
          type="button"
        >
          {title}
        </button>
      </h1>
    );
  }
  return (
    <span className="app-header__title-edit">
      <input
        aria-invalid={error !== null}
        aria-label="Sohbet adı"
        autoFocus
        className="app-header__title-input"
        disabled={saving}
        maxLength={200}
        onBlur={() => { if (!saving && error === null) void commit(); }}
        onChange={(event) => { setDraft(event.target.value); setError(null); }}
        onKeyDown={onKeyDown}
        value={draft}
      />
      {error && <span className="app-header__title-error" role="alert">{error}</span>}
    </span>
  );
}
