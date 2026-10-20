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

export const emptyRegistry: ProjectRegistry = { projects: [], chats: {} };

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

export function loadRegistry(storage: StorageLike | (() => StorageLike)): ProjectRegistry {
  try {
    const result = readStorage(typeof storage === "function" ? storage : () => storage, PROJECT_REGISTRY_KEY);
    if (!result.ok || !result.value) return emptyRegistry;
    const parsed = JSON.parse(result.value) as Record<string, unknown>;
    if (parsed.version !== REGISTRY_VERSION || !Array.isArray(parsed.projects)) return emptyRegistry;
    if (!parsed.projects.every(isRecord)) return emptyRegistry;
    const chats = parsed.chats;
    if (!chats || typeof chats !== "object" || Array.isArray(chats)) return emptyRegistry;
    const valid = Object.entries(chats as Record<string, unknown>)
      .filter((entry): entry is [string, string] => typeof entry[1] === "string");
    return { projects: parsed.projects, chats: Object.fromEntries(valid) };
  } catch {
    return emptyRegistry;
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
