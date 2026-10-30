import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { WorkspaceEntry, WorkspaceFile, WorkspaceState } from "./types";

const initialState: WorkspaceState = {
  directories: {},
  expanded: new Set<string>(),
  selected: null,
  loading: true,
  error: null,
  selectedError: null,
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

/** Tek dizin için çekilen en fazla sayfa; 200 × 50 = 10.000 girdi. */
const MAX_LISTING_PAGES = 50;
const PAGE_SIZE = 200;

/**
 * Dizini sayfa sayfa sonuna kadar okur. Ölçüldü (30 Ekim): tek `limit: 200` sayfası çekiliyor,
 * 200'den fazla girdili dizinde (`node_modules`, `assets`) kalan dosyalar sessizce görünmüyordu (U4-42).
 */
async function listDirectory(
  client: ProtocolClient,
  path: string,
): Promise<{ entries: WorkspaceEntry[]; truncated: boolean }> {
  const entries: WorkspaceEntry[] = [];
  let cursor = 0;
  for (let page = 0; page < MAX_LISTING_PAGES; page += 1) {
    const result = await client.request("proje.listele", { yol: path, cursor, limit: PAGE_SIZE });
    entries.push(...entriesFrom(result));
    const next = result.next_cursor;
    if (result.has_more !== true || typeof next !== "number" || next <= cursor) return { entries, truncated: false };
    cursor = next;
  }
  return { entries, truncated: true };
}

const TRUNCATED_NOTICE = `Çok büyük klasör: yalnız ilk ${MAX_LISTING_PAGES * PAGE_SIZE} girdi gösteriliyor.`;

/** CRLF'li dosya textarea'da LF'ye dönüşür; kaydederken özgün satır sonu geri konur (U4-44). */
function restoreLineEndings(original: string | null, edited: string): string {
  if (!original || !original.includes("\r\n") || /(^|[^\r])\n/.test(original)) return edited;
  return edited.replace(/\r?\n/g, "\r\n");
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
    const { entries, truncated } = await listDirectory(client, path);
    if (owner.current !== current || !current.active) return entries;
    setState((current) => ({
      ...current,
      directories: { ...current.directories, [path]: entries },
      loading: false,
      error: truncated ? TRUNCATED_NOTICE : null,
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
      listDirectory(client, ""),
    ]).then(([, listing]) => {
      if (!active || owner.current !== current) return;
      setState({
        ...initialState,
        directories: { "": listing.entries },
        loading: false,
        error: listing.truncated ? TRUNCATED_NOTICE : null,
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
      const { entries, truncated } = await listDirectory(client, path);
      return [path, entries, truncated] as const;
    })).then((listings) => {
      if (owner.current !== current || !current.active || refresh.current !== sequence) return;
      setState((value) => {
        // Açık olmayan ama önbellekteki dizinler bayatladı: düşürülür, yeniden açılınca taze okunur (U4-43).
        const taze = new Set(paths);
        const korunan = Object.fromEntries(Object.entries(value.directories).filter(([path]) => taze.has(path)));
        return {
          ...value,
          directories: { ...korunan, ...Object.fromEntries(listings.map(([path, entries]) => [path, entries])) },
          error: listings.some(([, , truncated]) => truncated) ? TRUNCATED_NOTICE : null,
        };
      });
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
    setState((current) => ({ ...current, loading: true, error: null, selectedError: null }));
    try {
      const result = await client.request("proje.oku", { yol: path });
      if (owner.current !== current || !current.active || current.selection !== sequence) return;
      // fileFrom updater İÇİNDE çağrılırsa geçersiz/ok:false cevap render sırasında fırlar ve
      // bileşen çöker (ölçüldü 29 Ekim: boş ekran); try/catch'e girmesi için dışarıda çözülür.
      const file = fileFrom(result);
      setState((current) => ({ ...current, selected: file, selectedError: null, loading: false }));
    } catch (reason) {
      // Tek dosyanın okuma hatası ağacı etkilemez (U4-02); eski dosya da yanıltmasın diye bırakılır.
      if (owner.current === current && current.active && current.selection === sequence) {
        setState((value) => ({ ...value, selected: null, selectedError: String(reason), loading: false }));
      }
    }
  }, [client]);

  const saveSelected = useCallback(async (content: string) => {
    const currentOwner = owner.current, selection = currentOwner.selection;
    const selected = state.selected;
    if (!selected || selected.tur !== "metin") throw new Error("Düzenlenebilir dosya seçilmedi.");
    // Kesilmiş içerikle kaydetmek dosyanın gösterilmeyen kısmını siler.
    if (selected.kesildi) throw new Error("Dosyanın yalnız bir bölümü açık; kısmi içerik kaydedilemez.");
    const result = await client.request("proje.yaz", {
      yol: selected.yol,
      icerik: restoreLineEndings(selected.icerik, content),
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
        icerik: restoreLineEndings(selected.icerik, content),
        sha256: result.sha256 as string,
        boyut: new TextEncoder().encode(restoreLineEndings(selected.icerik, content)).length,
        kesildi: false,
      } : null,
      error: null,
    }));
    return { ...result, gorunum_guncel: true };
  }, [client, state.selected]);

  return { state, saveSelected, selectFile, toggleDirectory };
}
