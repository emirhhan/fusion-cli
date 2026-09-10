import { useMemo, useState } from "react";
import type { CatalogEntry } from "./catalog";

export function ConnectorSetupForm({
  busy,
  entry,
  onCancel,
  onSubmit,
}: {
  busy: boolean;
  entry: CatalogEntry;
  onCancel: () => void;
  onSubmit: (values: Readonly<Record<string, string>>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const complete = useMemo(
    () => (entry.setup ?? []).every((field) => Boolean(values[field.id]?.trim())),
    [entry.setup, values],
  );

  return (
    <section aria-label={`${entry.label} kurulumu`} className="connectors__custom">
      <div className="connectors__custom-head">
        <div>
          <h3>{entry.label} kurulumu</h3>
          <p>Bağlantı için gereken alanları doldur. Gizli değerler şifreli depoda saklanır.</p>
        </div>
        <button className="connectors__custom-close" onClick={onCancel} type="button">
          Vazgeç
        </button>
      </div>
      <div className="connectors__custom-form">
        {(entry.setup ?? []).map((field) => (
          <label key={field.id}>
            <span>{field.label}</span>
            <input
              autoComplete="off"
              onChange={(event) =>
                setValues((current) => ({ ...current, [field.id]: event.target.value }))
              }
              placeholder={field.placeholder}
              type={field.secret ? "password" : "text"}
              value={values[field.id] ?? ""}
            />
          </label>
        ))}
        <button
          className="connectors__custom-submit"
          disabled={busy || !complete}
          onClick={() => onSubmit(values)}
          type="button"
        >
          Bağlantıyı ekle
        </button>
      </div>
    </section>
  );
}
