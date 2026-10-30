import type { VoiceWindowGeometry, VoiceWindowSnapshot } from "./windowBridge";

export const VOICE_GEOMETRY_KEY = "fusion.talk.window.v2";
export const DEFAULT_VOICE_GEOMETRY: VoiceWindowGeometry = {
  normalHeight: 460,
  normalWidth: 380,
  onTop: true,
  wide: false,
  x: null,
  y: null,
};

function finite(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function readVoiceGeometry(storage: Storage): VoiceWindowGeometry {
  try {
    const raw = JSON.parse(storage.getItem(VOICE_GEOMETRY_KEY) ?? "null") as Partial<VoiceWindowGeometry> | null;
    if (!raw) return { ...DEFAULT_VOICE_GEOMETRY };
    return {
      normalHeight: finite(raw.normalHeight, DEFAULT_VOICE_GEOMETRY.normalHeight),
      normalWidth: finite(raw.normalWidth, DEFAULT_VOICE_GEOMETRY.normalWidth),
      // "Hep üstte kal" tercihi kalıcıdır (U2-21); yalnız `wide` hâlâ sabit: Talk tek (mini) yerleşimdir
      // ve eski sürümlerden kalan `wide:true` kullanıcıyı çıkış olmayan bir yerleşime hapsederdi.
      onTop: typeof raw.onTop === "boolean" ? raw.onTop : DEFAULT_VOICE_GEOMETRY.onTop,
      wide: false,
      x: typeof raw.x === "number" && Number.isFinite(raw.x) ? raw.x : null,
      y: typeof raw.y === "number" && Number.isFinite(raw.y) ? raw.y : null,
    };
  } catch {
    return { ...DEFAULT_VOICE_GEOMETRY };
  }
}

export function saveVoiceGeometry(storage: Storage, geometry: VoiceWindowGeometry): void {
  // Özel pencerede/kotada `setItem` fırlatabilir; pencere taşıma olayında bu yakalanmamış kalmamalı (U2-22).
  try { storage.setItem(VOICE_GEOMETRY_KEY, JSON.stringify(geometry)); } catch { /* konum hatırlanmaz; Talk çalışır */ }
}

export function mergeVoiceSnapshot(
  geometry: VoiceWindowGeometry,
  snapshot: VoiceWindowSnapshot,
): VoiceWindowGeometry {
  return {
    ...geometry,
    ...(geometry.wide ? { normalHeight: snapshot.height, normalWidth: snapshot.width } : {}),
    x: snapshot.x,
    y: snapshot.y,
  };
}
