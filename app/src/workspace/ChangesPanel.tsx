import { useCallback, useEffect, useRef, useState } from "react";
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
  /** Verilirse panelde iş-akışı makroları (`/security-review`, `/simplify`) düğme olarak sunulur. */
  onCommand?: (line: string) => void;
  revision: number;
}

/** Değişiklikler panelinden tek tıkla başlatılan yerleşik makrolar (çekirdekle aynı adlar). */
export const CHANGES_MACROS: readonly { etiket: string; komut: string; aciklama: string }[] = [
  { etiket: "Güvenlik incelemesi", komut: "/security-review", aciklama: "Değişiklikleri OWASP başlıklarıyla tara" },
  { etiket: "Sadeleştir", komut: "/simplify", aciklama: "Değişen kodu yeniden kullanım ve verimlilik için sadeleştir" },
];

function MacroBar({ onCommand }: { onCommand?: (line: string) => void }) {
  if (!onCommand) return null;
  return (
    <div aria-label="İş-akışı makroları" className="changes-panel__macros" role="group">
      {CHANGES_MACROS.map((macro) => (
        <button key={macro.komut} onClick={() => onCommand(macro.komut)} title={macro.aciklama} type="button">
          {macro.etiket}
        </button>
      ))}
    </div>
  );
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

export function ChangesPanel({ client, onChanged, onCommand, revision }: ChangesPanelProps) {
  const [changes, setChanges] = useState<ChangeItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmPath, setConfirmPath] = useState<string | null>(null);
  //: Geri alma hatası listeyi SİLMEZ; diğer dosyalara erişim sürer ve yeniden denenebilir (U4-45).
  const [actionError, setActionError] = useState<string | null>(null);
  const sequence = useRef(0);
  const loaded = useRef(false);

  const refresh = useCallback(async () => {
    // Yalnız ilk yüklemede "yükleniyor" gösterilir; sonraki yenilemeler listeyi sökmez (açık onay
    // ve kaydırma korunur). Geç gelen eski yanıt yenisini ezmez.
    const mine = ++sequence.current;
    if (!loaded.current) setLoading(true);
    try {
      const next = decode(await client.request("proje.degisiklikler", {}));
      if (mine !== sequence.current) return;
      setChanges(next);
      setError(null);
      loaded.current = true;
    } catch (reason) {
      if (mine === sequence.current) setError(String(reason));
    } finally {
      if (mine === sequence.current) setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    void refresh();
  }, [refresh, revision]);

  if (loading) return <p className="changes-panel__state">Değişiklikler yükleniyor…</p>;
  if (error) return <p className="changes-panel__state changes-panel__state--error" role="alert">{error}</p>;
  // Makro çubuğu oturumda değişiklik yokken de durur: güvenlik incelemesi `git diff`
  // üzerinden çalışır, kullanıcının elle yaptığı değişiklikleri de kapsar.
  if (changes.length === 0) {
    return (
      <div className="changes-panel">
        <MacroBar onCommand={onCommand} />
        <p className="changes-panel__state">Bu oturumda doğrudan düzenlenen dosya yok.</p>
      </div>
    );
  }

  return (
    <div className="changes-panel">
      <MacroBar onCommand={onCommand} />
      {actionError && <p className="changes-panel__state changes-panel__state--error" role="alert">{actionError}</p>}
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
                  setActionError(null);
                  void client.request("proje.geri_al", { yol: change.yol }).then((result) => {
                    if (result.ok !== true) throw new Error(String(result.metin ?? "Geri alınamadı."));
                    setConfirmPath(null);
                    onChanged?.();
                    return refresh();
                  }).catch((reason) => setActionError(reason instanceof Error ? reason.message : String(reason)));
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
