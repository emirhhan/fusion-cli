/** Uzaktan erişim kullanılıyor işareti: kurulmamış kullanıcıda `uzak.*` yoklaması hiç başlamaz. */
export const REMOTE_IN_USE_KEY = "fusion.remote.inuse";
/**
 * Bayrak değişince pencereye yayılan olay: başlık anahtarı (`useRemoteStatus`) oturum içinde ilk
 * kurulumu yeniden başlatmasız görür. Ölçüldü (31 Ekim): bayrak yalnız effect kurulurken okunuyordu.
 */
export const REMOTE_IN_USE_EVENT = "fusion:remote-inuse";

export function remoteInUse(storage?: Pick<Storage, "getItem">): boolean {
  try {
    return (storage ?? window.localStorage).getItem(REMOTE_IN_USE_KEY) === "1";
  } catch {
    return false;
  }
}

export function markRemoteInUse(on: boolean, storage?: Pick<Storage, "setItem" | "removeItem">): void {
  try {
    const depo = storage ?? window.localStorage;
    if (on) depo.setItem(REMOTE_IN_USE_KEY, "1");
    else depo.removeItem(REMOTE_IN_USE_KEY);
  } catch {
    // Depolama yoksa işaret tutulmaz; yoklama yalnız bu oturumda ayarlar panelinden açılır.
  }
  try {
    window.dispatchEvent(new CustomEvent(REMOTE_IN_USE_EVENT, { detail: on }));
  } catch {
    // Pencere yoksa (test dışı sunucu ortamı) dinleyen de yoktur.
  }
}

/** Bayrak değişimini dinle; `storage` olayı başka pencere/sekmedeki değişimi de taşır. */
export function onRemoteInUseChange(listener: (on: boolean) => void): () => void {
  const fromEvent = () => listener(remoteInUse());
  window.addEventListener(REMOTE_IN_USE_EVENT, fromEvent);
  window.addEventListener("storage", fromEvent);
  return () => {
    window.removeEventListener(REMOTE_IN_USE_EVENT, fromEvent);
    window.removeEventListener("storage", fromEvent);
  };
}
