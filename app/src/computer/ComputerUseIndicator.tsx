import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
import "./ComputerUseIndicator.css";

/**
 * "Fusion bilgisayarı kullanıyor" şeridi (P-033).
 *
 * Claude CLI computer use'daki "Claude is using your computer · press Esc to stop" bildiriminin
 * karşılığı. Çekirdek ilk fare/klavye eyleminde `BilgisayarKullaniliyor {aktif, esc}` yayar;
 * tur bitince ya da durdurulunca kapanır. Tur artık sürmüyorsa (iptal olayı kaçsa bile) şerit
 * kendiliğinden gizlenir. `esc` yalnız Esc dinleyicisi gerçekten kurulduysa gelir; Esc ile
 * durdurulan turda (`esc_ile_durdu`) bir sonraki tura kadar kısa bir not kalır.
 */

interface ComputerUseIndicatorProps {
  client: Pick<ProtocolClient, "onEvent">;
  running: boolean;
  onStop: () => void;
}

interface IndicatorState {
  active: boolean;
  esc: boolean;
  /** Tur fiziksel Esc ile durduruldu; bir sonraki tur başlayana kadar söylenir. */
  stoppedByEsc: boolean;
}

const IDLE: IndicatorState = { active: false, esc: false, stoppedByEsc: false };

export function ComputerUseIndicator({ client, running, onStop }: ComputerUseIndicatorProps) {
  const [state, setState] = useState<IndicatorState>(IDLE);

  useEffect(() => client.onEvent((event) => {
    if (event.olay !== "BilgisayarKullaniliyor") return;
    setState({ active: event.aktif === true, esc: event.esc === true, stoppedByEsc: event.esc_ile_durdu === true });
  }), [client]);

  useEffect(() => {
    // Tur bitince şerit kapanır (Esc notu kalır); yeni tur başlayınca not da silinir.
    setState((previous) => (running ? { ...previous, stoppedByEsc: false } : { ...previous, active: false, esc: false }));
  }, [running]);

  if (state.active && running) {
    return (
      <div className="computer-indicator" role="status">
        <span aria-hidden="true" className="computer-indicator__dot" />
        <span className="computer-indicator__text">
          Fusion bilgisayarı kullanıyor{state.esc ? " · durdurmak için Esc" : ""}
        </span>
        <Button onClick={onStop} variant="secondary">Durdur</Button>
      </div>
    );
  }
  if (state.stoppedByEsc && !running) {
    return (
      <div className="computer-indicator computer-indicator--stopped" role="status">
        <span className="computer-indicator__text">Esc ile durduruldu: Fusion bilgisayarı kullanmayı bıraktı.</span>
      </div>
    );
  }
  return null;
}
