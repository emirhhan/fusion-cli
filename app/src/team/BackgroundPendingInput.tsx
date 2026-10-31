import { useState, type FormEvent } from "react";

/** Arka plan görevinin bekleyen isteği (`soru.json`; `arkaplan.durum` satırında `soru`). */
export interface PendingRequest {
  kind: "onay" | "soru";
  summary: string;
  /** Onaylanacak çağrının TAM (redakte) argümanı; listedeki özet kırpılmış olabilir. */
  args: string;
  danger: string;
  options: string[];
  recommended: string;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Eski çekirdek `soru` göndermezse istek onay sayılır (önceki panel davranışı). */
export function parsePendingRequest(value: unknown, fallbackSummary: string): PendingRequest {
  const raw = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const options = Array.isArray(raw.secenekler) ? raw.secenekler.filter((item): item is string => typeof item === "string") : [];
  return {
    kind: raw.tur === "soru" ? "soru" : "onay",
    summary: text(raw.ozet) || fallbackSummary,
    args: text(raw.arguman),
    danger: text(raw.tehlike),
    options,
    recommended: text(raw.onerilen),
  };
}

interface PendingInputProps {
  taskName: string;
  request: PendingRequest;
  /** `arkaplan.cevapla` çağrısı; başarılıysa true. */
  onAnswer: (answer: string) => Promise<boolean>;
}

/**
 * Girdi bekleyen görevin isteği. Onayda karar düğmeleri + tam çağrı ve risk; soruda
 * seçenek düğmeleri ve serbest metin cevabı (CLI `fusion agents cevapla`, REPL `/tasks answer`).
 */
export function BackgroundPendingInput({ taskName, request, onAnswer }: PendingInputProps) {
  const [answer, setAnswer] = useState("");

  if (request.kind === "onay") {
    return (
      <div className="bg-agents__pending">
        {request.danger && <p className="bg-agents__danger">Risk: {request.danger}</p>}
        {request.args && (
          <details>
            <summary>Tam çağrı</summary>
            <pre aria-label={`${taskName} onaylanacak çağrı`} className="bg-agents__output">{request.args}</pre>
          </details>
        )}
        <div aria-label={`${taskName} onayı`} className="bg-agents__actions" role="group">
          <button onClick={() => void onAnswer("evet")} type="button">Onayla</button>
          <button onClick={() => void onAnswer("oturum")} type="button">Bu görevde hep</button>
          <button onClick={() => void onAnswer("hayir")} type="button">Reddet</button>
        </div>
      </div>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = answer.trim();
    if (value && (await onAnswer(value))) setAnswer("");
  };
  return (
    <div className="bg-agents__pending">
      {request.options.length > 0 && (
        <div aria-label={`${taskName} seçenekleri`} className="bg-agents__actions" role="group">
          {request.options.map((option) => (
            <button aria-pressed={option === request.recommended} key={option} onClick={() => void onAnswer(option)} type="button">
              {option}
            </button>
          ))}
        </div>
      )}
      <form className="bg-agents__reply" onSubmit={(event) => void submit(event)}>
        <input aria-label={`${taskName} sorusuna cevap`} onChange={(event) => setAnswer(event.target.value)} placeholder="Cevabını yaz" value={answer} />
        <button disabled={!answer.trim()} type="submit">Cevapla</button>
      </form>
    </div>
  );
}
