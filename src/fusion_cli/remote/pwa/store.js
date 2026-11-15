// Kalıcı depo: IndexedDB (CryptoKey doğrudan saklanır, dışa aktarılamaz).
const DB = "fusion-uzak";

// Tek bağlantı paylaşılır: her çağrıda yeni bağlantı açıp kapatmamak sızıntıydı (R1-35).
let dbPromise = null;
function openDb() {
  dbPromise ??= new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("kv");
    request.onsuccess = () => {
      request.result.onclose = () => { dbPromise = null; };
      resolve(request.result);
    };
    request.onerror = () => { dbPromise = null; reject(request.error); };
  });
  return dbPromise;
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
