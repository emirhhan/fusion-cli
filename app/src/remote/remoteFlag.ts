/** Uzaktan erişim kullanılıyor işareti: kurulmamış kullanıcıda `uzak.*` yoklaması hiç başlamaz. */
export const REMOTE_IN_USE_KEY = "fusion.remote.inuse";

export function remoteInUse(storage: Pick<Storage, "getItem"> = window.localStorage): boolean {
  try {
    return storage.getItem(REMOTE_IN_USE_KEY) === "1";
  } catch {
    return false;
  }
}

export function markRemoteInUse(on: boolean, storage: Pick<Storage, "setItem" | "removeItem"> = window.localStorage): void {
  try {
    if (on) storage.setItem(REMOTE_IN_USE_KEY, "1");
    else storage.removeItem(REMOTE_IN_USE_KEY);
  } catch {
    // Depolama yoksa işaret tutulmaz; yoklama yalnız bu oturumda ayarlar panelinden açılır.
  }
}
