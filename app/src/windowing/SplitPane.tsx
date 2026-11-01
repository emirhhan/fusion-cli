import { useState, type KeyboardEvent } from "react";
import { Approval } from "../dialogs/Approval";
import { Conversation } from "../screens/Conversation";
import type { SessionModel } from "../sessions/types";
import { Button } from "../ui/Button";
import "./SplitPane.css";

/**
 * İkinci sohbet bölmesi (P-064): yan yana iki sohbet.
 *
 * Bölme tam bir sohbettir: akış, onay kartı ve kısa bir mesaj kutusu. Dosya ağacı,
 * terminal ve denetçi aktif sohbete bağlı kalır; "Bu sohbete geç" ile bölmedeki
 * sohbet aktif yapılır. Aynı sohbet iki bölmede çizilmez (bkz. `splitView.ts`).
 */

export interface SplitPaneProps {
  session: Pick<SessionModel, "title" | "running" | "messages" | "question" | "status">;
  showSteps: boolean;
  onSend: (task: string) => void;
  onAnswer: (data: Record<string, unknown>) => void | Promise<void>;
  onFocus: () => void;
  onClose: () => void;
}

export function SplitPane({ session, showSteps, onSend, onAnswer, onFocus, onClose }: SplitPaneProps) {
  const [draft, setDraft] = useState("");
  const gonder = () => {
    const metin = draft.trim();
    if (!metin) return;
    onSend(metin);
    setDraft("");
  };
  const tus = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      gonder();
    }
  };
  return (
    <section aria-label={`${session.title} (yan bölme)`} className="split-pane">
      <header className="split-pane__header">
        <span className="split-pane__title">{session.title}</span>
        <span aria-live="polite" className="split-pane__status">{session.running ? "Çalışıyor" : "Hazır"}</span>
        <Button onClick={onFocus} variant="ghost">Bu sohbete geç</Button>
        <Button aria-label="Yan bölmeyi kapat" icon="close" iconOnly onClick={onClose} />
      </header>
      <div className="split-pane__body">
        {session.messages.length > 0
          ? <Conversation mesajlar={session.messages} running={session.running} showSteps={showSteps} />
          : <p className="split-pane__empty">Bu sohbette henüz mesaj yok.</p>}
        {session.question && (
          <Approval key={session.question.id} onCevap={onAnswer} soru={session.question.data} />
        )}
      </div>
      <form className="split-pane__composer" onSubmit={(event) => { event.preventDefault(); gonder(); }}>
        <textarea
          aria-label={`${session.title} sohbetine mesaj`}
          disabled={session.status !== "ready"}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={tus}
          placeholder={session.running ? "Tur sürüyor; mesaj sıraya girer…" : "Bu sohbete yaz… (Enter gönderir)"}
          rows={2}
          value={draft}
        />
        <Button disabled={!draft.trim() || session.status !== "ready"} type="submit" variant="primary">Gönder</Button>
      </form>
    </section>
  );
}
