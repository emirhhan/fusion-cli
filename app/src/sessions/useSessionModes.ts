import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { APPROVAL_MODES, type ApprovalMode } from "../screens/ApprovalModeMenu";
import { folderMode, rememberFolderMode } from "./folderModes";
import { saveWorkspaceMode, storedWorkspaceMode, type WorkspaceMode } from "./useSessions";

interface ActiveSession {
  id: string;
  /** Oturumun klasörü: seçilen izin modu klasör başına hatırlanır (#451). */
  root?: string;
  /** `onEvent` verilirse denetçinin kip düşüşü (P-011) arayüze anında yansır. */
  client: Pick<ProtocolClient, "request"> & Partial<Pick<ProtocolClient, "onEvent">>;
}

/** Oturum kişiliği (P-053): `oturum.durum.kisilik` → `{ad, unvan}` ya da null. */
export interface SessionPersona {
  ad: string;
  unvan: string;
}

/** `oturum.durum` / `oturum.baslat` cevabındaki mod alanlarını doğrulayarak okur. */
export function modlariOku(result: Record<string, unknown>): { approval?: ApprovalMode; workspace?: WorkspaceMode; persona?: SessionPersona | null } {
  const approval = APPROVAL_MODES.find((mode) => mode.id === result.mod)?.id;
  const workspace = result.kip === "sohbet" || result.kip === "kod" ? result.kip : undefined;
  return { approval, workspace, persona: kisilikOku(result) };
}

/** `kisilik` alanı: nesne → kişilik, null → kapalı, yok/bozuk → undefined (dokunma). */
export function kisilikOku(result: Record<string, unknown>): SessionPersona | null | undefined {
  if (!("kisilik" in result)) return undefined;
  const raw = result.kisilik;
  if (raw === null) return null;
  if (!raw || typeof raw !== "object") return undefined;
  const info = raw as Record<string, unknown>;
  if (typeof info.ad !== "string") return undefined;
  return { ad: info.ad, unvan: typeof info.unvan === "string" ? info.unvan : info.ad };
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
  const [personas, setPersonas] = useState<Record<string, SessionPersona | null>>({});
  const id = active?.id;
  const client = active?.client;
  const root = active?.root;
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
      const { approval, workspace, persona } = modlariOku(result);
      if (approval) setApprovals((current) => ({ ...current, [id]: approval }));
      // Klasörde hatırlanan mod (Plan hariç) `defaultMode`'u ezer (#451).
      const remembered = folderMode(root);
      if (remembered && approval && remembered !== approval) {
        void client.request("oturum.baslat", { mod: remembered }).then((changed) => {
          if (cancelled || changed.ok === false || changes.current !== stamp) return;
          const confirmed = modlariOku(changed).approval ?? remembered;
          setApprovals((current) => ({ ...current, [id]: confirmed }));
        }).catch(() => undefined);
      }
      if (persona !== undefined) setPersonas((current) => ({ ...current, [id]: persona }));
      if (workspace) {
        saveWorkspaceMode(id, workspace);
        setWorkspaces((current) => ({ ...current, [id]: workspace }));
      }
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [id, client, root]);

  useEffect(() => {
    if (!id || !client?.onEvent) return;
    // Otomatik kip denetçisi engel eşiğini aştı (P-011): çekirdek oturumu Manuel'e çekti.
    return client.onEvent((veri) => {
      if (veri.olay !== "AutoModeFellBack") return;
      changes.current += 1;
      setApprovals((current) => ({ ...current, [id]: "security" }));
    });
  }, [id, client]);

  /** Çekirdek kipi kendisi değiştirdiğinde (`oto.devam`) arayüz o kipi benimser. */
  const adoptApproval = useCallback((next: ApprovalMode) => {
    if (!id) return;
    changes.current += 1;
    setApprovals((current) => ({ ...current, [id]: next }));
  }, [id]);

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
    rememberFolderMode(root, confirmed);
    return true;
  }, [id, request, root]);

  const changeWorkspace = useCallback(async (next: WorkspaceMode): Promise<boolean> => {
    const result = await request({ kip: next }, "Sohbet kipi değiştirilemedi. Yeniden dene.");
    if (!result || !id) return false;
    saveWorkspaceMode(id, next);
    setWorkspaces((current) => ({ ...current, [id]: next }));
    return true;
  }, [id, request]);

  const changePersona = useCallback(async (next: string | null): Promise<boolean> => {
    const result = await request({ kisilik: next ?? "" }, "Oturum kişiliği değiştirilemedi.");
    if (!result || !id) return false;
    const confirmed = kisilikOku(result);
    setPersonas((current) => ({ ...current, [id]: confirmed === undefined ? (next ? { ad: next, unvan: next } : null) : confirmed }));
    return true;
  }, [id, request]);

  return {
    approval: (id ? approvals[id] : undefined) ?? folderMode(root) ?? "security" as ApprovalMode,
    workspaceMode: (id ? workspaces[id] ?? storedWorkspaceMode(id) : null) ?? "kod" as WorkspaceMode,
    persona: (id ? personas[id] : undefined) ?? null,
    changeApproval,
    adoptApproval,
    changeWorkspace,
    changePersona,
  };
}
