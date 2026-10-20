// Kalıcı depo: IndexedDB (CryptoKey doğrudan saklanır, dışa aktarılamaz).
const DB = "fusion-uzak";

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("kv");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function kv(mode, key, value) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const store = db.transaction("kv", mode === "get" ? "readonly" : "readwrite").objectStore("kv");
    const op = mode === "get" ? store.get(key) : mode === "put" ? store.put(value, key) : store.delete(key);
    op.onsuccess = () => resolve(op.result);
    op.onerror = () => reject(op.error);
  });
}
