import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { BrowserRequest } from "./BrowserPanel";

/**
 * Denetçideki Tarayıcı sekmesinin bağlantıları (P-045): önizlemeden "Tarayıcıda aç / Öğe seç"
 * isteği ve ajan tarayıcıyı ilk açtığında sekmeye geçiş (önizlemenin `PreviewReady` davranışı
 * gibi). Kullanıcı başka sekmeye dönerse tur içinde yeniden zorlanmaz.
 */
export interface BrowserInspector {
  request: BrowserRequest | null;
  openInBrowser: (url: string, pick?: boolean) => void;
}

export function useBrowserInspector(
  client: ProtocolClient,
  showBrowser: () => void,
): BrowserInspector {
  const [request, setRequest] = useState<BrowserRequest | null>(null);

  useEffect(() => {
    let shownThisTurn = false;
    return client.onEvent((event) => {
      if (event.olay === "TurnFinished") shownThisTurn = false;
      if (shownThisTurn || event.olay !== "ToolExecuted" || event.outcome !== "ok") return;
      if (event.name !== "browser_open" && event.name !== "browser_tab_open") return;
      shownThisTurn = true;
      showBrowser();
    });
  }, [client, showBrowser]);

  const openInBrowser = useCallback((url: string, pick = false) => {
    setRequest((current) => ({ url, pick, seq: (current?.seq ?? 0) + 1 }));
    showBrowser();
  }, [showBrowser]);

  return { request, openInBrowser };
}
