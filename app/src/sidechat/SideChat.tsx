import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./SideChat.css";

/**
 * Yan sohbet (#444; Claude Desktop ⌘; / Ctrl+;): ana sohbetten dallanır, onun bağlamını okur ama
 * ana sohbete hiçbir şey eklemez. Her soru `yan_sohbet.sor` ile araçsız tek model çağrısıdır;
 * yan sohbetin kendi geçmişi yalnız bu bölmede yaşar ve bölme kapanınca silinir.
 */
export interface SideTurn {
  rol: "kullanici" | "asistan";
  metin: string;
}

interface SideReply {
  ok: boolean;
  metin?: string;
}

export function SideChat({ client, onClose }: { client: ProtocolClient; onClose: () => void }) {
  const [turns, setTurns] = useState<SideTurn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { input.current?.focus(); }, []);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    setError("");
    try {
      const reply = await client.request("yan_sohbet.sor", { soru: question, gecmis: turns }) as unknown as SideReply;
      if (!reply.ok) throw new Error(reply.metin || "Yan soru yanıtlanamadı.");
      setTurns((previous) => [...previous, { rol: "kullanici", metin: question }, { rol: "asistan", metin: reply.metin ?? "" }]);
      setText("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Yan soru yanıtlanamadı.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside aria-label="Yan sohbet" className="side-chat" onKeyDown={(event) => { if (event.key === "Escape") onClose(); }}>
      <header className="side-chat__header">
        <h2>Yan sohbet</h2>
        <button aria-label="Yan sohbeti kapat" onClick={onClose} type="button">×</button>
      </header>
      <p className="side-chat__hint">Ana sohbeti okur, ona bir şey eklemez. Araç kullanmaz, dosyaya dokunmaz.</p>
      <ol className="side-chat__turns">
        {turns.map((turn, index) => (
          <li className={`side-chat__turn side-chat__turn--${turn.rol}`} key={index}>{turn.metin}</li>
        ))}
        {busy && <li className="side-chat__turn side-chat__turn--wait">Yanıtlanıyor…</li>}
      </ol>
      {error && <p className="side-chat__error" role="alert">{error}</p>}
      <form className="side-chat__form" onSubmit={(event) => void submit(event)}>
        <textarea
          aria-label="Yan soru"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); }
          }}
          placeholder="Ana görevi bozmadan sor…"
          ref={input}
          rows={2}
          value={text}
        />
        <button disabled={busy || !text.trim()} type="submit">Sor</button>
      </form>
    </aside>
  );
}
