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
 * Açılış ekranı: düz koyu zeminde ortada tek bir logo, başka hiçbir şey.
 *
 * Kurulum/denetim sürerken ekranda yazı, çubuk ya da yüzde YOKTUR; durum yalnız ekran okuyucu
 * için gizli metin olarak durur. Kullanıcıdan bir şey gerektiren durumlarda (onarım, hata)
 * logonun altında kısa bir açıklama ve tek bir eylem görünür.
 */
export function RuntimeSetup({ state, progress, message, version, onRepair }: RuntimeSetupProps) {
  const busy = state === "denetleniyor" || state === "kuruluyor";
  const repairable = state === "onarilabilir";
  const failed = state === "hata";
  const title = repairable ? "Çalışma zamanı onarılmalı" : failed ? "Fusion başlatılamadı" : "Fusion'ı hazırlıyoruz";

  return (
    <main className="runtime-setup" data-busy={busy} data-state={state}>
      <div className="runtime-setup__mark" aria-hidden="true">
        <Logo size={56} />
      </div>
      <section aria-labelledby="runtime-title" className="runtime-setup__notice" data-visible={!busy}>
        <h1 id="runtime-title">{title}</h1>
        <p className="runtime-setup__message" role={busy ? "status" : undefined}>{message}</p>
        {busy && (
          <div
            aria-label="Kurulum ilerlemesi"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={progress}
            role="progressbar"
          />
        )}
        {repairable && (
          <Button className="runtime-setup__repair" onClick={onRepair} variant="primary">
            Çalışma zamanını onar
          </Button>
        )}
        {(repairable || failed) && (
          <details className="runtime-setup__details">
            <summary>Ayrıntılar</summary>
            <p>{message}</p>
            {version && <p className="runtime-setup__version">Sürüm {version}</p>}
          </details>
        )}
      </section>
    </main>
  );
}
