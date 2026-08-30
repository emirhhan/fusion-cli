import { convertFileSrc } from "@tauri-apps/api/core";
import { kabukVar } from "../voice/bridge";

/**
 * Yerel bir dosya yolunu arayüzde gösterilebilir adrese çevirir.
 *
 * Tauri, dosya sistemine doğrudan `file://` ile erişilmesine izin vermez;
 * yol kendi varlık protokolüne çevrilmelidir. Kabuk yoksa (tarayıcı, test)
 * çeviri yapılamaz ve `null` döner — çağıran yerde önizleme yerine simge
 * gösterilir.
 */
export function assetUrl(path: string): string | null {
  if (!kabukVar()) return null;
  try {
    return convertFileSrc(path);
  } catch {
    return null;
  }
}
