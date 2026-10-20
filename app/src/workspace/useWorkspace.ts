import { useCallback, useEffect, useRef, useState } from "react";
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

export function useWorkspace(client: ProtocolClient, root: string, revision = 0) {
  const [state, setState] = useState<WorkspaceState>(initialState);
  const stateRef = useRef(state);
  stateRef.current = state;
  const owner = useRef({ client, root, active: true, selection: 0 });
  if (owner.current.client !== client || owner.current.root !== root) owner.current = { client, root, active: true, selection: 0 };
  const lastRevision = useRef({ owner: owner.current, revision });
  const refresh = useRef(0);

  const loadDirectory = useCallback(async (path: string) => {
    const current = owner.current;
    const result = await client.request("proje.listele", { yol: path, cursor: 0, limit: 200 });
    const entries = entriesFrom(result);
    if (owner.current !== current || !current.active) return entries;
    setState((current) => ({
      ...current,
      directories: { ...current.directories, [path]: entries },
      loading: false,
      error: null,
    }));
    return entries;
  }, [client]);

  useEffect(() => {
    const current = owner.current;
    current.active = true;
    let active = true;
    setState(initialState);
    void Promise.all([
      client.request("proje.durum", {}),
      client.request("proje.listele", { yol: "", cursor: 0, limit: 200 }),
    ]).then(([, listing]) => {
      if (!active || owner.current !== current) return;
      setState({
        ...initialState,
        directories: { "": entriesFrom(listing) },
        loading: false,
      });
    }).catch((reason) => {
      if (active && owner.current === current) setState({ ...initialState, loading: false, error: String(reason) });
    });
    return () => {
      active = false;
      current.active = false;
    };
  }, [client, root]);

  useEffect(() => {
    const current = owner.current;
    const previous = lastRevision.current;
    lastRevision.current = { owner: current, revision };
    if (previous.owner !== current || previous.revision === revision) return;
    const sequence = ++refresh.current;
    const paths = ["", ...stateRef.current.expanded];
    void Promise.all(paths.map(async (path) => {
      const result = await client.request("proje.listele", { yol: path, cursor: 0, limit: 200 });
      return [path, entriesFrom(result)] as const;
    })).then((listings) => {
      if (owner.current !== current || !current.active || refresh.current !== sequence) return;
      setState((value) => ({ ...value, directories: { ...value.directories, ...Object.fromEntries(listings) }, error: null }));
    }).catch((reason) => {
      if (owner.current === current && current.active && refresh.current === sequence) setState((value) => ({ ...value, error: String(reason) }));
    });
  }, [client, root, revision]);

  const toggleDirectory = useCallback(async (path: string) => {
    const current = owner.current;
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
      if (owner.current !== current || !current.active) return;
      setState((current) => ({ ...current, expanded: new Set([...current.expanded, path]) }));
    } catch (reason) {
      if (owner.current === current && current.active) setState((value) => ({ ...value, error: String(reason), loading: false }));
    }
  }, [loadDirectory, state.directories, state.expanded]);

  const selectFile = useCallback(async (path: string) => {
    const current = owner.current, sequence = ++current.selection;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const result = await client.request("proje.oku", { yol: path });
      if (owner.current !== current || !current.active || current.selection !== sequence) return;
      setState((current) => ({ ...current, selected: fileFrom(result), loading: false }));
    } catch (reason) {
      if (owner.current === current && current.active && current.selection === sequence) setState((value) => ({ ...value, error: String(reason), loading: false }));
    }
  }, [client]);

  const saveSelected = useCallback(async (content: string) => {
    const currentOwner = owner.current, selection = currentOwner.selection;
    const selected = state.selected;
    if (!selected || selected.tur !== "metin") throw new Error("Düzenlenebilir dosya seçilmedi.");
    const result = await client.request("proje.yaz", {
      yol: selected.yol,
      icerik: content,
      expected_sha256: selected.sha256,
    });
    if (result.ok !== true || typeof result.sha256 !== "string") {
      throw new Error(messageFrom(result, "Dosya kaydedilemedi."));
    }
    if (owner.current !== currentOwner || !currentOwner.active || currentOwner.selection !== selection) return { ...result, gorunum_guncel: false };
    setState((current) => ({
      ...current,
      selected: current.selected ? {
        ...current.selected,
        icerik: content,
        sha256: result.sha256 as string,
        boyut: new TextEncoder().encode(content).length,
        kesildi: false,
      } : null,
      error: null,
    }));
    return { ...result, gorunum_guncel: true };
  }, [client, state.selected]);

  return { state, saveSelected, selectFile, toggleDirectory };
}
