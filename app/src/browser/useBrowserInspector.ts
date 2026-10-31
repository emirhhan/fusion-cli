import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { BrowserRequest } from "./BrowserPanel";
import { BROWSER_RPC } from "./browserPanelProtocol";

/**
 * Denetçideki Tarayıcı sekmesinin bağlantıları (P-045): önizlemeden "Tarayıcıda aç / Öğe seç"
 * isteği ve ajan tarayıcıyı ilk açtığında sekmeye geçiş (önizlemenin `PreviewReady` davranışı
 * gibi). Kullanıcı başka sekmeye dönerse tur içinde yeniden zorlanmaz. Geçiş yalnız ajan
 * paneli paylaşıyorsa (`ajan_goruyor`) olur.
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
    let active = true;
    const unsubscribe = client.onEvent((event) => {
      if (event.olay === "TurnFinished") shownThisTurn = false;
      if (shownThisTurn || event.olay !== "ToolExecuted" || event.outcome !== "ok") return;
      if (event.name !== "browser_open" && event.name !== "browser_tab_open") return;
      shownThisTurn = true;
      // Ajan paneli paylaşmıyorsa (kapalı ya da onaysız girişli oturum) kendi tarayıcısını
      // açar: panel onu göstermez, sekmeye geçmek boş ekran gösterirdi.
      void client.request(`${BROWSER_RPC}durum`, {})
        .then((payload) => {
          if (active && payload.ok === true && payload.ajan_goruyor === true) showBrowser();
          else shownThisTurn = false;
        })
        .catch(() => { shownThisTurn = false; });
    });
    return () => { active = false; unsubscribe(); };
  }, [client, showBrowser]);

  const openInBrowser = useCallback((url: string, pick = false) => {
    setRequest((current) => ({ url, pick, seq: (current?.seq ?? 0) + 1 }));
    showBrowser();
  }, [showBrowser]);

  return { request, openInBrowser };
}
