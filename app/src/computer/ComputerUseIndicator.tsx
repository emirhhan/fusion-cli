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
 * kendiliğinden gizlenir.
 */

interface ComputerUseIndicatorProps {
  client: Pick<ProtocolClient, "onEvent">;
  running: boolean;
  onStop: () => void;
}

export function ComputerUseIndicator({ client, running, onStop }: ComputerUseIndicatorProps) {
  const [state, setState] = useState<{ active: boolean; esc: boolean }>({ active: false, esc: false });

  useEffect(() => client.onEvent((event) => {
    if (event.olay !== "BilgisayarKullaniliyor") return;
    setState({ active: event.aktif === true, esc: event.esc === true });
  }), [client]);

  useEffect(() => {
    if (!running) setState({ active: false, esc: false });
  }, [running]);

  if (!state.active || !running) return null;
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
