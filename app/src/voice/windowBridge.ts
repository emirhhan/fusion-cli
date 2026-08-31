import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

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

export async function minimizeVoiceWindow(): Promise<void> {
  await invoke("ses_penceresi_simge_durumu");
}

export async function startSpeechRecognition(): Promise<void> {
  await invoke("tanima_baslat");
}

export async function stopSpeechRecognition(): Promise<void> {
  await invoke("tanima_durdur");
}

export async function getSpeechRecognitionStatus(): Promise<boolean> {
  return invoke<boolean>("tanima_durum");
}

export interface VoiceWindowGeometry {
  x: number | null;
  y: number | null;
  normalWidth: number;
  normalHeight: number;
  wide: boolean;
  onTop: boolean;
}

export interface VoiceWindowSnapshot {
  height: number;
  width: number;
  x: number;
  y: number;
}

/** localStorage'dan okunan Talk geometrisini tek native işlemde geri uygular. */
export async function applyVoiceWindowGeometry(geometry: VoiceWindowGeometry): Promise<void> {
  await invoke("ses_penceresi_geometri_uygula", { geometry });
}

/** Taşınma/boyutlanmayı retina fiziksel pikselinden mantıksal piksele çevirir. */
export async function onVoiceWindowGeometryChanged(
  handler: (snapshot: VoiceWindowSnapshot) => void,
): Promise<() => void> {
  const current = getCurrentWindow();
  const publish = async () => {
    const [position, size, scale] = await Promise.all([
      current.outerPosition(),
      current.innerSize(),
      current.scaleFactor(),
    ]);
    handler({
      height: size.height / scale,
      width: size.width / scale,
      x: position.x / scale,
      y: position.y / scale,
    });
  };
  const [removeMoved, removeResized] = await Promise.all([
    current.onMoved(() => { void publish(); }),
    current.onResized(() => { void publish(); }),
  ]);
  return () => { removeMoved(); removeResized(); };
}

/** Panel ölçüsü: dar yalnız karakter, geniş döküm ve ayarlar. */
export async function setVoiceWindowWide(genis: boolean): Promise<void> {
  await invoke("ses_penceresi_boyut", { genis });
}

/** Panel hep üstte mi kalsın? */
export async function setVoiceWindowOnTop(ustte: boolean): Promise<void> {
  await invoke("ses_penceresi_ustte", { ustte });
}
