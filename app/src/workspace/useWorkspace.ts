import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { WorkspaceEntry, WorkspaceFile, WorkspaceState } from "./types";

const initialState: WorkspaceState = {
  directories: {},
  expanded: new Set<string>(),
  selected: null,
  loading: true,
  error: null,
};

function messageFrom(payload: Record<string, unknown>, fallback: string): string {
  return typeof payload.metin === "string" && payload.metin ? payload.metin : fallback;
}

function entriesFrom(payload: Record<string, unknown>): WorkspaceEntry[] {
  if (payload.ok !== true || !Array.isArray(payload.girdiler)) {
    throw new Error(messageFrom(payload, "Proje dosyaları alınamadı."));
  }
  return payload.girdiler.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("Geçersiz dosya kaydı alındı.");
    const item = raw as Record<string, unknown>;
    if (
      typeof item.ad !== "string" ||
      typeof item.yol !== "string" ||
      (item.tur !== "klasor" && item.tur !== "dosya") ||
      typeof item.boyut !== "number" ||
      typeof item.degistirilme !== "number"
    ) {
      throw new Error("Geçersiz dosya kaydı alındı.");
    }
    return item as unknown as WorkspaceEntry;
  });
}

function fileFrom(payload: Record<string, unknown>): WorkspaceFile {
  if (payload.ok !== true) throw new Error(messageFrom(payload, "Dosya okunamadı."));
  if (
    typeof payload.yol !== "string" ||
    (payload.tur !== "metin" && payload.tur !== "binary") ||
    typeof payload.mime !== "string" ||
    typeof payload.boyut !== "number" ||
    typeof payload.sha256 !== "string" ||
    !(typeof payload.icerik === "string" || payload.icerik === null) ||
    typeof payload.kesildi !== "boolean"
  ) {
    throw new Error("Geçersiz dosya içeriği alındı.");
  }
  return payload as unknown as WorkspaceFile;
}

export function useWorkspace(client: ProtocolClient, root: string) {
  const [state, setState] = useState<WorkspaceState>(initialState);

  const loadDirectory = useCallback(async (path: string) => {
    const result = await client.request("proje.listele", { yol: path, cursor: 0, limit: 200 });
    const entries = entriesFrom(result);
    setState((current) => ({
      ...current,
      directories: { ...current.directories, [path]: entries },
      loading: false,
      error: null,
    }));
    return entries;
  }, [client]);

  useEffect(() => {
    let active = true;
    setState(initialState);
    void Promise.all([
      client.request("proje.durum", {}),
      client.request("proje.listele", { yol: "", cursor: 0, limit: 200 }),
    ]).then(([, listing]) => {
      if (!active) return;
      setState({
        ...initialState,
        directories: { "": entriesFrom(listing) },
        loading: false,
      });
    }).catch((reason) => {
      if (active) setState({ ...initialState, loading: false, error: String(reason) });
    });
    return () => {
      active = false;
    };
  }, [client, root]);

  const toggleDirectory = useCallback(async (path: string) => {
    if (state.expanded.has(path)) {
      setState((current) => {
        const expanded = new Set(current.expanded);
        expanded.delete(path);
        return { ...current, expanded };
      });
      return;
    }
    try {
      if (!state.directories[path]) await loadDirectory(path);
      setState((current) => ({ ...current, expanded: new Set([...current.expanded, path]) }));
    } catch (reason) {
      setState((current) => ({ ...current, error: String(reason), loading: false }));
    }
  }, [loadDirectory, state.directories, state.expanded]);

  const selectFile = useCallback(async (path: string) => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const result = await client.request("proje.oku", { yol: path });
      setState((current) => ({ ...current, selected: fileFrom(result), loading: false }));
    } catch (reason) {
      setState((current) => ({ ...current, error: String(reason), loading: false }));
    }
  }, [client]);

  return { state, selectFile, toggleDirectory };
}
