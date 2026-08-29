import { useMemo, useState } from "react";
import type { ProcessController } from "./useProcesses";
import "./processes.css";

export function TerminalPanel({ controller }: { controller: ProcessController }) {
  const [command, setCommand] = useState("");
  const latest = useMemo(
    () => controller.processes[controller.processes.length - 1] ?? null,
    [controller.processes],
  );

  return (
    <div className="terminal-panel">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!command.trim()) return;
          void controller.start(command.trim());
        }}
      >
        <span aria-hidden="true">$</span>
        <input
          aria-label="Terminal komutu"
          autoCapitalize="off"
          autoComplete="off"
          onChange={(event) => setCommand(event.target.value)}
          placeholder="npm test"
          spellCheck={false}
          value={command}
        />
        <button disabled={controller.busy || !command.trim()} type="submit">Çalıştır</button>
      </form>
      {controller.error && <p className="process-error" role="alert">{controller.error}</p>}
      <div aria-live="polite" className="terminal-panel__output">
        {latest ? (
          <>
            <header>
              <span>{latest.cwd} $ {latest.komut}</span>
              <small>{latest.durum}{latest.cikis_kodu === null ? "" : ` · ${latest.cikis_kodu}`}</small>
            </header>
            <pre>{latest.cikti || (latest.durum === "calisiyor" ? "Çalışıyor…" : "(çıktı yok)")}</pre>
          </>
        ) : (
          <p>Bu konuşmada henüz terminal komutu çalıştırılmadı.</p>
        )}
      </div>
    </div>
  );
}
