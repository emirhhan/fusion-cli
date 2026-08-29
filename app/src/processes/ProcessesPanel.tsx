import type { ProcessController } from "./useProcesses";
import "./processes.css";

export function ProcessesPanel({ controller }: { controller: ProcessController }) {
  if (controller.error) return <p className="process-error" role="alert">{controller.error}</p>;
  if (controller.processes.length === 0) return <p className="process-empty">Çalıştırılmış süreç yok.</p>;
  return (
    <div className="process-list">
      {controller.processes.map((process) => (
        <article key={process.surec_id}>
          <div>
            <strong>{process.komut}</strong>
            <span>PID {process.pid} · {process.cwd}</span>
          </div>
          <div>
            <span className={`process-status process-status--${process.durum}`}>{process.durum}</span>
            {process.durum === "calisiyor" && (
              <button onClick={() => void controller.stop(process.surec_id)} type="button">Durdur</button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
