/** Uzaktan erişim kullanılıyor işareti: kurulmamış kullanıcıda `uzak.*` yoklaması hiç başlamaz. */
export const REMOTE_IN_USE_KEY = "fusion.remote.inuse";

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
}
