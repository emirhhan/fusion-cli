import { useEffect } from "react";
import { isMacOS } from "./os";

interface NativeWindowChrome {
  isFullscreen(): Promise<boolean>;
  onResized(callback: () => void): Promise<() => void>;
}

/** Tam ekranda sistem düğmeleri saklanınca başlıkta gereksiz boşluk bırakma. */
export async function syncWindowChrome(nativeWindow: NativeWindowChrome, root: HTMLElement): Promise<() => void> {
  let disposed = false;
  let revision = 0;
  const update = async () => {
    const request = ++revision;
    try {
      const fullscreen = await nativeWindow.isFullscreen();
      if (disposed || request !== revision) return;
      if (fullscreen) delete root.dataset.fusionTitlebarInset;
      else root.dataset.fusionTitlebarInset = "true";
    } catch {
      // Sistem sorgulanamazsa pencere düğmelerinin güvenli payını koru.
    }
  };
  const unlisten = await nativeWindow.onResized(() => { void update(); });
  await update();
  return () => { disposed = true; unlisten(); };
}

export function useWindowChrome(): void {
  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window) || !isMacOS()) return;
    let disposed = false;
    let stop: (() => void) | undefined;
    void import("@tauri-apps/api/window").then(({ getCurrentWindow }) =>
      syncWindowChrome(getCurrentWindow(), document.documentElement),
    ).then((cleanup) => {
      if (disposed) cleanup(); else stop = cleanup;
    }).catch(() => { /* Başlangıçtaki güvenli pencere payı korunur. */ });
    return () => { disposed = true; stop?.(); };
  }, []);
}
