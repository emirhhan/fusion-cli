import type { RuntimeState } from "../runtime/types";
import { Logo } from "../brand/Logo";
import { Button } from "../ui/Button";
import "../theme/tokens.css";
import "./RuntimeSetup.css";

interface RuntimeSetupProps {
  state: RuntimeState;
  progress: number;
  message: string;
  version?: string;
  onRepair: () => void;
}

/**
 * Açılış ekranı: koyu bir "aurora" zemin üzerinde camlı (buzlu) bir kart.
 *
 * Marka renkleri (mavi, camgöbeği, mor) yavaşça süzülen yumuşak ışık lekeleri olur; logo, dönen
 * renkli bir halkanın içinde durur. Hareketin tamamı `transform`/`opacity` ile yapılır ve
 * "hareketi azalt" ayarında durur. Kurulum yüzdesi kartın altında ince bir cam çubukta görünür.
 */
export function RuntimeSetup({ state, progress, message, version, onRepair }: RuntimeSetupProps) {
  const busy = state === "denetleniyor" || state === "kuruluyor";
  const repairable = state === "onarilabilir";
  const known = progress > 0;

  return (
    <main className="runtime-setup" data-busy={busy} data-state={state}>
      <div aria-hidden="true" className="runtime-setup__aurora">
        <i className="runtime-setup__orb runtime-setup__orb--blue" />
        <i className="runtime-setup__orb runtime-setup__orb--cyan" />
        <i className="runtime-setup__orb runtime-setup__orb--violet" />
      </div>
      <section className="runtime-setup__card" aria-labelledby="runtime-title">
        <div className="runtime-setup__mark" aria-hidden="true">
          <span className="runtime-setup__halo" />
          <span className="runtime-setup__disc">
            <Logo size={44} />
          </span>
        </div>
        <p aria-hidden="true" className="runtime-setup__eyebrow">FUSION</p>
        <h1 id="runtime-title">Fusion'ı hazırlıyoruz</h1>
        <p className="runtime-setup__message">{message}</p>
        {busy && (
          <div className="runtime-setup__progress">
            <div
              aria-label="Kurulum ilerlemesi"
              aria-valuemax={100}
              aria-valuemin={0}
              aria-valuenow={progress}
              className="runtime-setup__track"
              data-indeterminate={!known}
              role="progressbar"
            >
              <span style={known ? { transform: `scaleX(${Math.min(100, progress) / 100})` } : undefined} />
            </div>
            <span className="runtime-setup__percent">{known ? `%${progress}` : "Birazdan hazır"}</span>
          </div>
        )}
        {version && <p className="runtime-setup__version">Sürüm {version}</p>}
        {repairable && (
          <Button className="runtime-setup__repair" onClick={onRepair} variant="primary">
            Çalışma zamanını onar
          </Button>
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
