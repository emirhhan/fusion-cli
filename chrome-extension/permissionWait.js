// İnsan izni ağ taşımasından ayrıdır; her kart tek komuta ve tek bekleyişe aittir.
export const PERMISSION_KEY = "fusionPermission";
export const HUMAN_PERMISSION_WAIT_MS = 300_000;
export const PROGRESS_REQUEST_TIMEOUT_MS = 4000;
const PERMISSION_POLL_MS = 400;
let permissionWaitMs = HUMAN_PERMISSION_WAIT_MS;
/** Testler insan bekleme süresini kısaltabilir. */
export function setPermissionWait(ms) { permissionWaitMs = ms; }

export class PermissionWaitError extends Error {
  constructor(code, message) { super(message); this.name = "PermissionWaitError"; this.code = code; }
}

function permissionKey(identifier) { return `${PERMISSION_KEY}:${identifier}`; }

async function pendingPermission(identifier) {
  const key = permissionKey(identifier);
  return (await chrome.storage.session.get(key))[key];
}

/** Kartlar ayrı anahtarlardadır: eski cevabın/cleanup'ın yeni kartı silme yarışı yoktur. */
export async function currentPermission(now = Date.now()) {
  const records = await chrome.storage.session.get(null);
  return Object.entries(records).filter(([key, card]) => key.startsWith(`${PERMISSION_KEY}:`) &&
    card?.state === "pending" && card.expiresAt > now)
    .map(([, card]) => card).sort((first, second) => second.at - first.at)[0] || null;
}

/** Eski panel tıklaması yeni izin kartını kapatamaz. */
export async function answerPermission(identifier, state, now = Date.now()) {
  const pending = await pendingPermission(identifier);
  if (!pending || pending.id !== identifier || pending.state !== "pending" || pending.expiresAt <= now) return false;
  if (!["granted", "denied", "cancelled"].includes(state)) return false;
  await chrome.storage.session.set({[permissionKey(identifier)]: {...pending, state}});
  return true;
}

async function permitted(origin) {
  return /^https?:/.test(origin) && chrome.permissions.contains({origins: [`${origin}/*`]});
}

async function progress(context, identifier, state) {
  if (!context.onProgress) return;
  let result;
  try { result = await context.onProgress({id: context.commandId, bekleme_id: identifier, durum: state}); }
  catch {
    throw new PermissionWaitError("permission_disconnected", "İzin beklerken Fusion bağlantısı koptu; komut iptal edildi.");
  }
  if (result?.baglanti_hatasi) {
    throw new PermissionWaitError("permission_disconnected", "İzin beklerken Fusion bağlantısı koptu; komut iptal edildi.");
  }
  if (!result?.ok || result.aktif === false) {
    throw new PermissionWaitError("permission_cancelled", "Bu komut artık etkin değil; geç gelen izin komutu yeniden başlatmadı.");
  }
}

/** Saat ve bekleme testlerde enjekte edilir; gerçek kullanıcıya beş dakika tanınır. */
export async function ensurePermission(origin, reason, context = {}, timing = {
  now: () => Date.now(), sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  if (await permitted(origin)) return;
  const identifier = crypto.randomUUID();
  const until = timing.now() + permissionWaitMs;
  await chrome.storage.session.set({[permissionKey(identifier)]: {
    id: identifier, commandId: context.commandId || "", origin, at: timing.now(), expiresAt: until, state: "pending",
  }});
  try {
    await progress(context, identifier, "permission_wait");
    for (;;) {
      const pending = await pendingPermission(identifier);
      if (!pending || pending.id !== identifier || pending.state === "cancelled") {
        throw new PermissionWaitError("permission_cancelled", `${reason} İzin bekleme iptal edildi.`);
      }
      if (pending.state === "denied") {
        throw new PermissionWaitError("permission_denied", `${reason} Kullanıcı ${origin} iznini açıkça reddetti.`);
      }
      if (timing.now() >= until) {
        throw new PermissionWaitError("permission_timeout", `${reason} İzin bekleme süresi doldu; kullanıcı reddetmiş sayılmadı.`);
      }
      if (await permitted(origin)) {
        // İzin tarayıcıya verilmiş olsa da durmuş eski komut yürütülemez.
        await progress(context, identifier, "permission_done");
        return;
      }
      await progress(context, identifier, "permission_wait");
      await timing.sleep(Math.min(PERMISSION_POLL_MS, until - timing.now()));
    }
  } finally {
    await chrome.storage.session.remove(permissionKey(identifier));
  }
}
