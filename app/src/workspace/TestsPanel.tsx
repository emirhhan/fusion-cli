import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ProcessController } from "../processes/useProcesses";
import "./TestsPanel.css";

interface SuggestedCommand { tur: string; ad: string; komut: string }

/**
 * "Bu oturumda hep çalıştır" denen komutlar, proje (istemci) başına bellekte tutulur. Öneriler
 * proje dosyalarından (package.json betikleri vb.) türer ve güvenilmeyen bir depodan gelebilir;
 * ilk çalıştırmada komut gösterilip onay istenir (U4-49b). Uygulama kapanınca unutulur.
 */
const REMEMBERED_COMMANDS = new WeakMap<ProtocolClient, Set<string>>();

function rememberedFor(client: ProtocolClient): Set<string> {
  let known = REMEMBERED_COMMANDS.get(client);
  if (!known) {
    known = new Set();
    REMEMBERED_COMMANDS.set(client, known);
  }
  return known;
}
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

export function TestsPanel({ client, processes, revision = 0 }: { client: ProtocolClient; processes: ProcessController; revision?: number }) {
  const [commands, setCommands] = useState<SuggestedCommand[]>([]);
  const [git, setGit] = useState<GitState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<SuggestedCommand | null>(null);

  const requestRun = (command: SuggestedCommand) => {
    if (rememberedFor(client).has(command.komut)) void processes.start(command.komut);
    else setPending(command);
  };
  const confirmRun = (remember: boolean) => {
    if (!pending) return;
    if (remember) rememberedFor(client).add(pending.komut);
    void processes.start(pending.komut);
    setPending(null);
  };

  useEffect(() => {
    let active = true;
    setLoading(true);
    setPending(null);
    setCommands([]);
    setGit(null);
    setError(null);
    // Git yok/bozuk depo öneri komutlarını gizlemez: iki okuma bağımsızdır (U4-49).
    void Promise.allSettled([
      client.request("proje.komut_onerileri", {}).then(commandsFrom),
      client.request("proje.git_durum", {}).then(gitFrom),
    ]).then(([commandResult, gitResult]) => {
      if (!active) return;
      if (commandResult.status === "rejected") {
        setError(String(commandResult.reason));
      } else {
        setCommands(commandResult.value);
        setError(null);
      }
      if (gitResult.status === "fulfilled") setGit(gitResult.value);
      setLoading(false);
    });
    return () => { active = false; };
  }, [client, revision]);

  if (loading) return <p role="status">Proje doğrulamaları yükleniyor…</p>;
  if (error) return <p className="tests-panel__error" role="alert">{error}</p>;
  return (
    <div className="tests-panel">
      {git && (
        <section aria-label="Git durumu" className="tests-panel__git">
          <strong>{git.git ? (git.branch ?? "detached HEAD") : "Git kullanılmıyor"}</strong>
          {git.git && <span>{git.degisen} değişiklik · ↑{git.ileride} ↓{git.geride}</span>}
        </section>
      )}
      {pending && (
        <section aria-label="Komut onayı" className="tests-panel__confirm" role="alertdialog">
          <p>Bu komut proje dosyalarından geliyor ve bilgisayarında çalışacak:</p>
          <code>{pending.komut}</code>
          <div className="tests-panel__confirm-actions">
            <button onClick={() => confirmRun(false)} type="button">Çalıştır</button>
            <button onClick={() => confirmRun(true)} type="button">Bu oturumda hep çalıştır</button>
            <button onClick={() => setPending(null)} type="button">Vazgeç</button>
          </div>
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
            onClick={() => requestRun(command)}
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
