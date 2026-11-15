import { readStorage, writeStorage } from "../platform/storage";

/**
 * Kalıcı proje kaydı.
 *
 * Proje artık klasör adından türemez: kullanıcının verdiği ad ve isteğe bağlı
 * bir klasörle durur. Sohbet kaydına dokunulmaz (orada yalnız `root` vardır);
 * hangi sohbetin hangi projede olduğu ayrı bir eşlemede tutulur. Eşlemesi
 * olmayan sohbet "Sohbetler" altındadır, eski kayıtlar bu yüzden aynen çalışır.
 */
export const PROJECT_REGISTRY_KEY = "fusion.projects.v1";
const REGISTRY_VERSION = 1;
export const PROJECT_NAME_MAX = 80;

export interface ProjectRecord {
  id: string;
  name: string;
  /** Verilmediyse proje sohbetleri Desktop içinde açılır. */
  root?: string;
  createdAt: number;
}

export interface ProjectRegistry {
  projects: ProjectRecord[];
  /** sohbet kimliği → proje kimliği */
  chats: Record<string, string>;
}

// Paylaşılan başlangıç değeri: yanlışlıkla değiştirilip tüm çağıranlara sızmasın diye dondurulur.
export const emptyRegistry: ProjectRegistry = Object.freeze({
  projects: Object.freeze([]) as unknown as ProjectRecord[],
  chats: Object.freeze({}) as Record<string, string>,
});

type StorageLike = Pick<Storage, "getItem" | "setItem">;

const sameName = (left: string, right: string) =>
  left.toLocaleLowerCase("tr") === right.toLocaleLowerCase("tr");

function cleanName(registry: ProjectRegistry, name: string, ownId?: string): string {
  const clean = name.trim();
  if (!clean) throw new Error("Proje adı boş olamaz.");
  if (clean.length > PROJECT_NAME_MAX) throw new Error(`Proje adı en fazla ${PROJECT_NAME_MAX} karakter olabilir.`);
  if (registry.projects.some((item) => item.id !== ownId && sameName(item.name, clean))) {
    throw new Error("Bu adla bir proje zaten var.");
  }
  return clean;
}

function requireProject(registry: ProjectRegistry, id: string): ProjectRecord {
  const found = registry.projects.find((item) => item.id === id);
  if (!found) throw new Error("Proje bulunamadı.");
  return found;
}

export function addProject(
  registry: ProjectRegistry,
  input: { id: string; name: string; root?: string; now: number },
): ProjectRegistry {
  const name = cleanName(registry, input.name);
  const root = input.root;
  const record: ProjectRecord = { id: input.id, name, ...(root ? { root } : {}), createdAt: input.now };
  return { ...registry, projects: [...registry.projects, record] };
}

export function renameProject(registry: ProjectRegistry, id: string, name: string): ProjectRegistry {
  requireProject(registry, id);
  const clean = cleanName(registry, name, id);
  return {
    ...registry,
    projects: registry.projects.map((item) => (item.id === id ? { ...item, name: clean } : item)),
  };
}

/** Projeyi siler; sohbetleri silinmez, yalnız projeden çıkar. */
export function removeProject(registry: ProjectRegistry, id: string): ProjectRegistry {
  return {
    projects: registry.projects.filter((item) => item.id !== id),
    chats: Object.fromEntries(Object.entries(registry.chats).filter(([, projectId]) => projectId !== id)),
  };
}

/** `projectId` null ise sohbet projeden çıkar. */
export function assignChat(registry: ProjectRegistry, chatId: string, projectId: string | null): ProjectRegistry {
  if (projectId === null) return forgetChat(registry, chatId);
  requireProject(registry, projectId);
  return { ...registry, chats: { ...registry.chats, [chatId]: projectId } };
}

export function forgetChat(registry: ProjectRegistry, chatId: string): ProjectRegistry {
  if (!(chatId in registry.chats)) return registry;
  const { [chatId]: _removed, ...rest } = registry.chats;
  return { ...registry, chats: rest };
}

function isRecord(value: unknown): value is ProjectRecord {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === "string" && typeof item.name === "string"
    && (item.root === undefined || typeof item.root === "string")
    && typeof item.createdAt === "number" && Number.isFinite(item.createdAt);
}

/** Okunamayan kaydın ilk ezilmeden önceki kopyası; kullanıcı/destek elle geri alabilir. */
export const PROJECT_REGISTRY_BACKUP_KEY = `${PROJECT_REGISTRY_KEY}.okunamayan-yedek`;

/**
 * Kayıt okunamıyorsa (bozuk JSON, bilinmeyen sürüm) boş kayıt döner; ama ilk `commit` bunu
 * depolamaya yazıp mevcut proje listesini KALICI ezeceğinden ham değer önce yedeklenir.
 * Ölçüldü (30 Ekim): tek bozuk kayıt ya da daha yeni sürümden geri dönüş tüm listeyi siliyordu (U4-41).
 */
function backupUnreadable(storage: StorageLike, raw: string): void {
  try {
    if (storage.getItem(PROJECT_REGISTRY_BACKUP_KEY) === null) storage.setItem(PROJECT_REGISTRY_BACKUP_KEY, raw);
  } catch { /* Yedek alınamazsa yükleme yine boş kayıtla sürer. */ }
}

export function loadRegistry(storage: StorageLike | (() => StorageLike)): ProjectRegistry {
  const access = typeof storage === "function" ? storage : () => storage;
  try {
    const result = readStorage(access, PROJECT_REGISTRY_KEY);
    if (!result.ok || !result.value) return { projects: [], chats: {} };
    let parsed: Record<string, unknown> | null = null;
    try { parsed = JSON.parse(result.value) as Record<string, unknown>; } catch { parsed = null; }
    if (!parsed || parsed.version !== REGISTRY_VERSION || !Array.isArray(parsed.projects)) {
      backupUnreadable(access(), result.value);
      return { projects: [], chats: {} };
    }
    // Biçim dışı tek kayıt ayıklanır; sağlam projeler ve eşlemeleri korunur.
    const projects = parsed.projects.filter(isRecord);
    if (projects.length !== parsed.projects.length) backupUnreadable(access(), result.value);
    const chats = parsed.chats;
    const valid = chats && typeof chats === "object" && !Array.isArray(chats)
      ? Object.entries(chats as Record<string, unknown>)
        .filter((entry): entry is [string, string] => typeof entry[1] === "string")
      : [];
    return { projects, chats: Object.fromEntries(valid) };
  } catch {
    return { projects: [], chats: {} };
  }
}

export function saveRegistry(storage: StorageLike | (() => StorageLike), registry: ProjectRegistry): void {
  try {
    writeStorage(
      typeof storage === "function" ? storage : () => storage,
      PROJECT_REGISTRY_KEY,
      JSON.stringify({ version: REGISTRY_VERSION, ...registry }),
    );
  } catch {
    // Depolama yoksa kayıt bu pencere açıkken bellekte kalır.
  }
}
