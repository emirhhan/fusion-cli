import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ProcessController } from "../processes/useProcesses";
import "./TestsPanel.css";

interface SuggestedCommand { tur: string; ad: string; komut: string }
interface GitState { git: boolean; branch: string | null; degisen: number; ileride: number; geride: number }

function commandsFrom(payload: Record<string, unknown>): SuggestedCommand[] {
  if (payload.ok !== true || !Array.isArray(payload.komutlar)) throw new Error("Komutlar alınamadı.");
  return payload.komutlar.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("Geçersiz komut kaydı.");
    const item = raw as Record<string, unknown>;
    if (typeof item.tur !== "string" || typeof item.ad !== "string" || typeof item.komut !== "string") {
      throw new Error("Geçersiz komut kaydı.");
    }
    return item as unknown as SuggestedCommand;
  });
}

function gitFrom(payload: Record<string, unknown>): GitState {
  if (
    payload.ok !== true || typeof payload.git !== "boolean" ||
    !(typeof payload.branch === "string" || payload.branch === null) ||
    typeof payload.degisen !== "number" || typeof payload.ileride !== "number" ||
    typeof payload.geride !== "number"
  ) throw new Error("Git durumu alınamadı.");
  return payload as unknown as GitState;
}

export function TestsPanel({ client, processes }: { client: ProtocolClient; processes: ProcessController }) {
  const [commands, setCommands] = useState<SuggestedCommand[]>([]);
  const [git, setGit] = useState<GitState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([
      client.request("proje.komut_onerileri", {}),
      client.request("proje.git_durum", {}),
    ]).then(([commandPayload, gitPayload]) => {
      if (!active) return;
      setCommands(commandsFrom(commandPayload));
      setGit(gitFrom(gitPayload));
      setError(null);
    }).catch((reason) => active && setError(String(reason)));
    return () => { active = false; };
  }, [client]);

  if (error) return <p className="tests-panel__error" role="alert">{error}</p>;
  return (
    <div className="tests-panel">
      {git && (
        <section aria-label="Git durumu" className="tests-panel__git">
          <strong>{git.git ? (git.branch ?? "detached HEAD") : "Git kullanılmıyor"}</strong>
          {git.git && <span>{git.degisen} değişiklik · ↑{git.ileride} ↓{git.geride}</span>}
        </section>
      )}
      <section aria-label="Proje doğrulamaları" className="tests-panel__commands">
        {commands.length === 0 ? (
          <p>Bu proje için otomatik bir doğrulama komutu bulunamadı. Terminalden komut yazabilirsin.</p>
        ) : commands.map((command) => (
          <button
            aria-label={command.ad}
            disabled={processes.busy}
            key={command.komut}
            onClick={() => void processes.start(command.komut)}
            type="button"
          >
            <span>{command.ad}</span>
            <code>{command.komut}</code>
          </button>
        ))}
      </section>
      <section aria-label="Doğrulama kanıtları" className="tests-panel__evidence">
        {processes.processes.length === 0 ? <p>Henüz doğrulama çalıştırılmadı.</p> :
          processes.processes.slice().reverse().map((process) => (
            <details key={process.surec_id} open={processes.processes.length === 1}>
              <summary>
                <span>{process.komut}</span>
                <strong data-status={process.durum}>{process.durum}</strong>
              </summary>
              <pre>{process.cikti || "(çıktı yok)"}</pre>
            </details>
          ))}
      </section>
    </div>
  );
}
