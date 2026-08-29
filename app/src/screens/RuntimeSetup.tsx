import type { RuntimeState } from "../runtime/types";
import "../theme/tokens.css";
import "./RuntimeSetup.css";

interface RuntimeSetupProps {
  state: RuntimeState;
  progress: number;
  message: string;
  version?: string;
  onRepair: () => void;
}

export function RuntimeSetup({ state, progress, message, version, onRepair }: RuntimeSetupProps) {
  const busy = state === "denetleniyor" || state === "kuruluyor";
  const repairable = state === "onarilabilir";

  return (
    <main className="runtime-setup">
      <section className="runtime-setup__card" aria-labelledby="runtime-title">
        <div className="runtime-setup__mark" aria-hidden="true">
          <span />
          <span />
        </div>
        <h1 id="runtime-title">Fusion'ı hazırlıyoruz</h1>
        <p className="runtime-setup__message">{message}</p>
        {busy && (
          <div className="runtime-setup__progress">
            <progress
              aria-label="Kurulum ilerlemesi"
              aria-valuenow={progress}
              max={100}
              value={progress}
            />
            <span>{progress > 0 ? `%${progress}` : "Birazdan hazır"}</span>
          </div>
        )}
        {version && <p className="runtime-setup__version">Sürüm {version}</p>}
        {repairable && (
          <button className="runtime-setup__repair" onClick={onRepair} type="button">
            Çalışma zamanını onar
          </button>
        )}
        {(repairable || state === "hata") && (
          <details className="runtime-setup__details">
            <summary>Ayrıntılar</summary>
            <p>{message}</p>
          </details>
        )}
      </section>
    </main>
  );
}
