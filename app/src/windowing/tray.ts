import { useEffect, useSyncExternalStore } from "react";
import { invoke } from "@tauri-apps/api/core";
import { kabukVar } from "../voice/bridge";

/**
 * Sistem tepsisi tercihi ve köprüsü (P-064).
 *
 * Varsayılan açık (Claude/Codex masaüstünde menü çubuğu simgesi vardır); Ayarlar › Genel'den
 * kapatılır. Çalışan tur sayısı araç ipucuna yazılır. Tauri kabuğu yoksa hiçbir şey yapılmaz.
 */

export const TRAY_STORAGE_KEY = "fusion.tray.v1";

export function readTrayEnabled(storage?: Pick<Storage, "getItem">): boolean {
  try {
    return (storage ?? localStorage).getItem(TRAY_STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

export function saveTrayEnabled(enabled: boolean, storage?: Pick<Storage, "setItem">): void {
  try {
    (storage ?? localStorage).setItem(TRAY_STORAGE_KEY, String(enabled));
  } catch {
    // Kalıcılaşmasa da bu pencerede uygulanır.
  }
}

const aboneler = new Set<() => void>();
let anlik: boolean | null = null;

export function getTrayEnabled(): boolean {
  if (anlik === null) anlik = readTrayEnabled();
  return anlik;
}

export function subscribeTray(listener: () => void): () => void {
  aboneler.add(listener);
  return () => {
    aboneler.delete(listener);
  };
}

export function setTrayEnabled(enabled: boolean): void {
  anlik = enabled;
  saveTrayEnabled(enabled);
  for (const listener of aboneler) listener();
}

export function resetTrayCache(): void {
  anlik = null;
}

export function useTrayEnabled(): boolean {
  return useSyncExternalStore(subscribeTray, getTrayEnabled, getTrayEnabled);
}

export interface TepsiKoprusu {
  ayarla: (acik: boolean) => Promise<void>;
  durum: (calisan: number) => Promise<void>;
}

const varsayilanKopru: TepsiKoprusu = {
  ayarla: (acik) => invoke("tepsi_ayarla", { acik }),
  durum: (calisan) => invoke("tepsi_durum", { calisan }),
};

/** Tercihi ve çalışan tur sayısını Rust tepsisine yansıt. */
export function useTray(runningCount: number, kopru: TepsiKoprusu = varsayilanKopru, kabuk: () => boolean = kabukVar): void {
  const enabled = useTrayEnabled();
  useEffect(() => {
    if (!kabuk()) return;
    kopru.ayarla(enabled).catch((error: unknown) => console.warn("Tepsi simgesi ayarlanamadı", error));
  }, [enabled, kopru, kabuk]);
  useEffect(() => {
    if (!kabuk() || !enabled) return;
    kopru.durum(runningCount).catch((error: unknown) => console.warn("Tepsi durumu yazılamadı", error));
  }, [runningCount, enabled, kopru, kabuk]);
}
