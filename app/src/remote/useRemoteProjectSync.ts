import { useEffect } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ProjectRegistry } from "../sessions/projectRecords";
import { remoteInUse } from "./remoteFlag";

/** Masaüstü proje kaydını çekirdeğe iletir; telefon aynı projeleri ve sohbet eşlemesini görür. */
export function useRemoteProjectSync(client: ProtocolClient | null, registry: ProjectRegistry): void {
  useEffect(() => {
    if (!client || !remoteInUse()) return;
    void client
      .request("uzak.projeler_esitle", { projeler: registry.projects, sohbetler: registry.chats })
      .catch(() => {
        // Eşitleme başarısızsa telefon son bilinen kaydı gösterir; sonraki değişiklikte yeniden denenir.
      });
  }, [client, registry]);
}
