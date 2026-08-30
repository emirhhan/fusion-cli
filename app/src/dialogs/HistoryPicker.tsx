import { useEffect, useMemo, useRef, useState } from "react";
import type { HistorySessionRef, HistorySourceName } from "../history/types";
import type { HistoryController } from "../history/useHistory";
import { SourceIcon } from "../brand/SourceIcon";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import "./HistoryPicker.css";

const SOURCE_LABELS: Record<HistorySourceName, string> = {
  claude: "Claude",
  codex: "Codex",
  hermes: "Hermes",
};

interface HistoryPickerProps {
  history: HistoryController;
  onClose: () => void;
  onResume: (session: HistorySessionRef) => Promise<{ id: string; secretCount: number }>;
  open: boolean;
}

function formatDate(timestamp: number | null): string {
  if (timestamp === null) return "Tarih yok";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(timestamp * 1000));
}

export function HistoryPicker({ history, onClose, onResume, open }: HistoryPickerProps) {
  const dialog = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [secretCount, setSecretCount] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    dialog.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  const sessions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("tr");
    if (!normalized) return history.sessions;
    return history.sessions.filter((session) =>
      session.baslik.toLocaleLowerCase("tr").includes(normalized),
    );
  }, [history.sessions, query]);

  if (!open) return null;

  const resume = async () => {
    if (!history.selected || resuming) return;
    setResuming(true);
    setResumeError(null);
    try {
      const result = await onResume(history.selected);
      setSecretCount(result.secretCount);
    } catch (reason) {
      setResumeError(String(reason));
    } finally {
      setResuming(false);
    }
  };

  return (
    <div className="history-picker-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div
        aria-labelledby="history-picker-title"
        aria-modal="true"
        className="history-picker"
        ref={dialog}
        role="dialog"
        tabIndex={-1}
      >
        <header className="history-picker__header">
          <div>
            <p className="history-picker__eyebrow">Geçmişten devam et</p>
            <h2 id="history-picker-title">Bir konuşma seçin</h2>
            <p>Bilgisayarınızda bulunan araçlardan bir konuşmayı önizleyip Fusion’da sürdürebilirsiniz.</p>
          </div>
          <button aria-label="Kapat" className="history-picker__close" onClick={onClose} type="button">
            <span aria-hidden="true">×</span>
          </button>
        </header>

        <div className="history-picker__body">
          <aside aria-label="Geçmiş kaynakları" className="history-picker__sources">
            {history.sources.map((source) => (
              <button
                aria-label={SOURCE_LABELS[source.ad]}
                className="history-picker__source"
                data-active={history.source === source.ad}
                key={source.ad}
                onClick={() => void history.openSource(source.ad)}
                type="button"
              >
                <span className="history-picker__source-mark"><SourceIcon size={20} source={source.ad} /></span>
                <span>
                  <strong>{SOURCE_LABELS[source.ad]}</strong>
                  <small>{source.komut}</small>
                </span>
              </button>
            ))}
          </aside>

          <section aria-label="Konuşmalar" className="history-picker__sessions">
            <label className="history-picker__search">
              <Icon name="search" size={17} />
              <input
                aria-label="Geçmiş konuşmalarda ara"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Konuşmalarda ara"
                type="search"
                value={query}
              />
            </label>
            <div className="history-picker__session-list">
              {!history.source && <p className="history-picker__empty">Önce bir kaynak seçin.</p>}
              {history.source && sessions.length === 0 && !history.loading && (
                <p className="history-picker__empty">Bu kaynakta gösterilecek konuşma bulunamadı.</p>
              )}
              {sessions.map((session) => (
                <button
                  aria-label={session.baslik}
                  className="history-picker__session"
                  data-active={history.selected?.oturum_id === session.oturum_id}
                  key={session.oturum_id}
                  onClick={() => void history.selectSession(session)}
                  type="button"
                >
                  <strong>{session.baslik}</strong>
                  <span>
                    <time>{formatDate(session.guncellendi)}</time>
                    {session.tur_sayisi !== null && <span>{session.tur_sayisi} tur</span>}
                  </span>
                </button>
              ))}
              {history.sessionCursor !== null && (
                <Button loading={history.loading} onClick={() => void history.loadMoreSessions()}>
                  Daha fazla konuşma
                </Button>
              )}
            </div>
          </section>

          <section aria-label="Konuşma önizlemesi" className="history-picker__preview">
            {!history.selected ? (
              <div className="history-picker__empty history-picker__empty--preview">
                <Icon name="preview" size={24} />
                <p>İçeriğini görmek için bir konuşma seçin.</p>
              </div>
            ) : (
              <>
                <div className="history-picker__preview-heading">
                  <span>[{history.selected.kaynak}]</span>
                  <h3>{history.selected.baslik}</h3>
                </div>
                <div className="history-picker__turns">
                  {history.turns.map((turn, index) => (
                    <article className="history-picker__turn" data-role={turn.rol} key={`${turn.zaman}-${index}`}>
                      <strong>{turn.rol === "user" ? "Siz" : "Asistan"}</strong>
                      <p>{turn.metin}</p>
                    </article>
                  ))}
                  {history.turnCursor !== null && (
                    <Button loading={history.loading} onClick={() => void history.loadMoreTurns()}>
                      Önizlemenin devamı
                    </Button>
                  )}
                </div>
              </>
            )}
          </section>
        </div>

        {(history.error || resumeError || secretCount !== null) && (
          <div aria-live="polite" className="history-picker__notice" data-error={Boolean(history.error || resumeError)}>
            {history.error || resumeError || ((secretCount ?? 0) > 0
              ? `${secretCount} hassas değer fark edildi. Fusion bunları ekranda göstermedi; uygun olduğunda ilgili anahtarları yenilemeniz iyi olur.`
              : "Konuşma hazır. Kaldığınız yerden devam edebilirsiniz.")}
          </div>
        )}

        <footer className="history-picker__footer">
          <Button onClick={onClose} variant="ghost">Vazgeç</Button>
          {secretCount !== null ? (
            <Button onClick={onClose} variant="primary">Konuşmaya geç</Button>
          ) : (
            <Button
              disabled={!history.selected}
              loading={resuming}
              onClick={() => void resume()}
              variant="primary"
            >
              Bu konuşmayı devral
            </Button>
          )}
        </footer>
      </div>
    </div>
  );
}
