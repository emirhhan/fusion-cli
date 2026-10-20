import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./ChangesPanel.css";

interface ChangeItem {
  yol: string;
  diff: string;
  added: number;
  removed: number;
  geri_alinabilir: boolean;
}

interface ChangesPanelProps {
  client: ProtocolClient;
  onChanged?: () => void;
  revision: number;
}

function decode(payload: Record<string, unknown>): ChangeItem[] {
  if (payload.ok !== true || !Array.isArray(payload.degisiklikler)) {
    throw new Error(typeof payload.metin === "string" ? payload.metin : "Değişiklikler alınamadı.");
  }
  return payload.degisiklikler.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("Geçersiz değişiklik kaydı.");
    const item = raw as Record<string, unknown>;
    if (
      typeof item.yol !== "string" ||
      typeof item.diff !== "string" ||
      typeof item.added !== "number" ||
      typeof item.removed !== "number" ||
      typeof item.geri_alinabilir !== "boolean"
    ) throw new Error("Geçersiz değişiklik kaydı.");
    return item as unknown as ChangeItem;
  });
}

export function ChangesPanel({ client, onChanged, revision }: ChangesPanelProps) {
  const [changes, setChanges] = useState<ChangeItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmPath, setConfirmPath] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setChanges(decode(await client.request("proje.degisiklikler", {})));
      setError(null);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    void refresh();
  }, [refresh, revision]);

  if (loading) return <p className="changes-panel__state">Değişiklikler yükleniyor…</p>;
  if (error) return <p className="changes-panel__state changes-panel__state--error" role="alert">{error}</p>;
  if (changes.length === 0) return <p className="changes-panel__state">Bu oturumda doğrudan düzenlenen dosya yok.</p>;

  return (
    <div className="changes-panel">
      {changes.map((change) => (
        <article className="changes-panel__item" key={change.yol}>
          <header>
            <strong>{change.yol}</strong>
            <span>+{change.added} −{change.removed}</span>
          </header>
          <pre>{change.diff.split("\n").map((line, index) => (
            <span className={line.startsWith("+") ? "is-added" : line.startsWith("-") ? "is-removed" : ""} key={`${index}-${line}`}>
              {line || " "}
            </span>
          ))}</pre>
          {!change.geri_alinabilir ? (
            <p className="changes-panel__note">Bu değişiklik yalnız okunabilir.</p>
          ) : confirmPath === change.yol ? (
            <div aria-label="Geri alma onayı" className="changes-panel__confirm" role="group">
              <span>Dosya bu oturumdan önceki sürümüne dönecek.</span>
              <button onClick={() => setConfirmPath(null)} type="button">Vazgeç</button>
              <button
                onClick={() => {
                  void client.request("proje.geri_al", { yol: change.yol }).then((result) => {
                    if (result.ok !== true) throw new Error(String(result.metin ?? "Geri alınamadı."));
                    setConfirmPath(null);
                    onChanged?.();
                    return refresh();
                  }).catch((reason) => setError(String(reason)));
                }}
                type="button"
              >
                Geri almayı onayla
              </button>
            </div>
          ) : (
            <button onClick={() => setConfirmPath(change.yol)} type="button">
              Bu dosyayı geri al
            </button>
          )}
        </article>
      ))}
    </div>
  );
}
