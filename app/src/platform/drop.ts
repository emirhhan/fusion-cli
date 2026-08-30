import { getCurrentWebview } from "@tauri-apps/api/webview";

/** Tauri'nin masaüstü sürükle-bırak olayından gerçek yerel yolları alır. */
export async function listenForFileDrops(handler: (paths: string[]) => void): Promise<() => void> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return () => undefined;
  return getCurrentWebview().onDragDropEvent((event) => {
    if (event.payload.type === "drop" && event.payload.paths.length > 0) {
      handler(event.payload.paths);
    }
  });
}
