import { invoke } from "@tauri-apps/api/core";

/**
 * Konuşma penceresi köprüsü.
 *
 * Konuşma kipi uygulama İÇİNDE bir katman değildir: ana pencere gerçekten
 * simge durumuna küçülür (macOS'taki sarı düğmenin yaptığı) ve konuşma için
 * ayrı, küçük, üstte kalan bir pencere açılır. Kullanıcı istediği anda ana
 * pencereyi geri getirir; oturumlar ve çalışan tur kapanmaz.
 */

/** Bu belge konuşma penceresinde mi çiziliyor? */
export function isVoiceWindow(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("pencere") === "ses";
}

export async function openVoiceWindow(): Promise<void> {
  await invoke("ses_penceresi_ac");
}

export async function closeVoiceWindow(): Promise<void> {
  await invoke("ses_penceresi_kapat");
}
