import { useCallback, useEffect, useState } from "react";

/**
 * Bölünmüş görünüm durumu (P-064): ana sohbetin yanında ikinci bir sohbet.
 *
 * Yalnız kimlik saklanır (pencere düzeni); sohbetin kendisi oturum deposundadır.
 * Aktif sohbetle aynı kimlik ikinci bölmeye alınmaz (aynı sohbeti iki kez çizmek
 * onay kartını ikiye katlar). Saklı kimlik açık değilse bölme kapalı başlar.
 */

export const SPLIT_STORAGE_KEY = "fusion.split.v1";

export function readSplitId(storage?: Pick<Storage, "getItem">): string | null {
  try {
    const value = (storage ?? localStorage).getItem(SPLIT_STORAGE_KEY);
    return value && /^[A-Za-z0-9_-]{1,128}$/.test(value) ? value : null;
  } catch {
    return null;
  }
}

export function saveSplitId(id: string | null, storage?: Pick<Storage, "setItem" | "removeItem">): void {
  try {
    const depo = storage ?? localStorage;
    if (id) depo.setItem(SPLIT_STORAGE_KEY, id);
    else depo.removeItem(SPLIT_STORAGE_KEY);
  } catch {
    // Düzen kalıcılaşmasa da bu pencerede uygulanır.
  }
}

/** Hangi kimlik ikinci bölmede gösterilecek: aktifle çakışırsa ya da kapalıysa null. */
export function resolveSplitId(splitId: string | null, activeId: string | null, openIds: ReadonlySet<string>): string | null {
  if (!splitId || splitId === activeId || !openIds.has(splitId)) return null;
  return splitId;
}

export function useSplitView(activeId: string | null, openIds: ReadonlySet<string>) {
  const [splitId, setSplitId] = useState<string | null>(readSplitId);
  useEffect(() => saveSplitId(splitId), [splitId]);
  const open = useCallback((id: string) => setSplitId(id), []);
  const close = useCallback(() => setSplitId(null), []);
  return { splitId: resolveSplitId(splitId, activeId, openIds), rawSplitId: splitId, open, close };
}
