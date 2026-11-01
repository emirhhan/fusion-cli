import { useCallback, useEffect, useRef, useState } from "react";

/** Arşivlenen sohbetlerin kalıcı anahtarı (sabitlemeyle aynı kaynak:kimlik biçimi). */
export const ARCHIVED_SESSIONS_KEY = "fusion.sidebar.archived-sessions.v1";

function readArchived(): string[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(ARCHIVED_SESSIONS_KEY) ?? "[]");
    return Array.isArray(saved) ? [...new Set(saved.filter((item): item is string => typeof item === "string"))] : [];
  } catch {
    return [];
  }
}

/**
 * Claude Desktop'taki Archive/Unarchive (#443): arşivlenen sohbet ana listeden kalkar,
 * "Arşivlenenler" görünümünde durur; silinmez. Tercih bu bilgisayarda saklanır.
 */
export function useArchivedSessions() {
  const [archived, setArchived] = useState<string[]>(readArchived);
  const [error, setError] = useState<string | null>(null);
  // Açılışta okunan liste yeniden yazılmaz: yalnız kullanıcı değiştirince kaydedilir.
  const loaded = useRef(archived);
  useEffect(() => {
    if (archived === loaded.current) return;
    try {
      localStorage.setItem(ARCHIVED_SESSIONS_KEY, JSON.stringify(archived));
      setError(null);
    } catch {
      setError("Arşiv tercihi kaydedilemedi; bu pencere açıkken korunacak.");
    }
  }, [archived]);
  const toggle = (key: string) => setArchived((current) => (
    current.includes(key) ? current.filter((item) => item !== key) : [...current, key]
  ));
  const forget = (key: string) => setArchived((current) => current.filter((item) => item !== key));
  /** Otomatik arşiv (#443): verilen sohbetleri arşive ekle (zaten arşivde olan değişmez). */
  const archiveMany = useCallback((keys: string[]) => setArchived((current) => {
    const added = keys.filter((key) => !current.includes(key));
    return added.length ? [...current, ...added] : current;
  }), []);
  return { archived, isArchived: (key: string) => archived.includes(key), toggle, forget, archiveMany, error };
}
