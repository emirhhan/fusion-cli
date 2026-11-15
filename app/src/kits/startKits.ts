import { invoke } from "@tauri-apps/api/core";

export type StartKits = () => Promise<{ url: string }>;

/** `kits_baslat` çalışan süreci yeniden kullanır; süren başlatmayı aynı kilitte bekler. */
export const startKitsWithTauri: StartKits = () => invoke<{ url: string }>("kits_baslat");
