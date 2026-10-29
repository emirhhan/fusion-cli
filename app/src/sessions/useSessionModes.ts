import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { APPROVAL_MODES, type ApprovalMode } from "../screens/ApprovalModeMenu";
import { saveWorkspaceMode, storedWorkspaceMode, type WorkspaceMode } from "./useSessions";

interface ActiveSession {
  id: string;
  client: Pick<ProtocolClient, "request">;
}

/** `oturum.durum` / `oturum.baslat` cevabındaki mod alanlarını doğrulayarak okur. */
export function modlariOku(result: Record<string, unknown>): { approval?: ApprovalMode; workspace?: WorkspaceMode } {
  const approval = APPROVAL_MODES.find((mode) => mode.id === result.mod)?.id;
  const workspace = result.kip === "sohbet" || result.kip === "kod" ? result.kip : undefined;
  return { approval, workspace };
}

/**
 * Sohbet başına izin modu ve çalışma kipi.
 *
 * Ölçüldü (29 Ekim): izin modu tek global `useState("auto")` idi — başka sohbete
 * geçince arayüz eski değeri gösterirken o sohbetin çekirdeği kendi modunda
 * çalışıyordu; değişiklik `ok:false` dönse de arayüz yeni modu gösteriyordu.
 * Artık (1) sohbet etkinleşince çekirdeğin gerçek durumu (`oturum.durum`) okunur,
 * (2) değişiklik ÇEKİRDEK onaylayınca görünür; reddedilirse eski görünüm kalır ve
 * `onError` ile hata bildirilir.
 */
export function useSessionModes(active: ActiveSession | null, onError: (message: string | null) => void) {
  const [approvals, setApprovals] = useState<Record<string, ApprovalMode>>({});
  const [workspaces, setWorkspaces] = useState<Record<string, WorkspaceMode>>({});
  const id = active?.id;
  const client = active?.client;
  const changes = useRef(0);
  const report = useRef(onError);
  report.current = onError;

  useEffect(() => {
    if (!id || !client) return;
    const stamp = changes.current;
    let cancelled = false;
    client.request("oturum.durum", {}).then((result) => {
      // Yanıt gelirken kullanıcı mod değiştirdiyse bayat durum onu ezmesin.
      if (cancelled || result.ok === false || changes.current !== stamp) return;
      const { approval, workspace } = modlariOku(result);
      if (approval) setApprovals((current) => ({ ...current, [id]: approval }));
      if (workspace) {
        saveWorkspaceMode(id, workspace);
        setWorkspaces((current) => ({ ...current, [id]: workspace }));
      }
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [id, client]);

  const request = useCallback(async (patch: Record<string, unknown>, failure: string): Promise<Record<string, unknown> | null> => {
    if (!id || !client) return null;
    changes.current += 1;
    try {
      const result = await client.request("oturum.baslat", patch);
      if (result.ok === false) {
        const reason = typeof result.metin === "string" && result.metin ? ` ${result.metin}` : "";
        report.current(`${failure}${reason}`);
        return null;
      }
      report.current(null);
      return result;
    } catch {
      report.current(failure);
      return null;
    }
  }, [id, client]);

  const changeApproval = useCallback(async (next: ApprovalMode): Promise<boolean> => {
    const result = await request({ mod: next }, "İzin modu değiştirilemedi.");
    if (!result || !id) return false;
    const confirmed = modlariOku(result).approval ?? next;
    setApprovals((current) => ({ ...current, [id]: confirmed }));
    return true;
  }, [id, request]);

  const changeWorkspace = useCallback(async (next: WorkspaceMode): Promise<boolean> => {
    const result = await request({ kip: next }, "Sohbet kipi değiştirilemedi. Yeniden dene.");
    if (!result || !id) return false;
    saveWorkspaceMode(id, next);
    setWorkspaces((current) => ({ ...current, [id]: next }));
    return true;
  }, [id, request]);

  return {
    approval: (id ? approvals[id] : undefined) ?? "auto" as ApprovalMode,
    workspaceMode: (id ? workspaces[id] ?? storedWorkspaceMode(id) : null) ?? "kod" as WorkspaceMode,
    changeApproval,
    changeWorkspace,
  };
}
