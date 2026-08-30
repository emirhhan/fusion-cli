import type { VoiceWindowGeometry, VoiceWindowSnapshot } from "./windowBridge";

export const VOICE_GEOMETRY_KEY = "fusion.talk.window.v1";
export const DEFAULT_VOICE_GEOMETRY: VoiceWindowGeometry = {
  normalHeight: 460,
  normalWidth: 380,
  onTop: true,
  wide: true,
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
      onTop: typeof raw.onTop === "boolean" ? raw.onTop : true,
      wide: typeof raw.wide === "boolean" ? raw.wide : true,
      x: typeof raw.x === "number" && Number.isFinite(raw.x) ? raw.x : null,
      y: typeof raw.y === "number" && Number.isFinite(raw.y) ? raw.y : null,
    };
  } catch {
    return { ...DEFAULT_VOICE_GEOMETRY };
  }
}

export function saveVoiceGeometry(storage: Storage, geometry: VoiceWindowGeometry): void {
  storage.setItem(VOICE_GEOMETRY_KEY, JSON.stringify(geometry));
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
