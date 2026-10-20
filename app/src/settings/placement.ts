/**
 * Çalışma panelinin yeri — sağda mı, altta mı.
 *
 * Kullanıcının isteği: panel sağda kalabilsin ama istendiğinde VS Code'daki
 * gibi görev kutusunun ALTINA inebilsin. Geniş bir terminal ya da uzun bir
 * diff, dar bir sağ sütunda okunmuyor.
 *
 * Tercih `theme.ts` ile aynı kalıptadır: okuma/yazma ayrı, depo enjekte
 * edilebilir ve erişim düşerse uygulama çalışmaya devam eder.
 */

export type InspectorPlacement = "right" | "bottom";

export const PLACEMENT_KEY = "fusion.inspector.placement";

export function readPlacement(storage: Pick<Storage, "getItem"> = localStorage): InspectorPlacement {
  try {
    return storage.getItem(PLACEMENT_KEY) === "bottom" ? "bottom" : "right";
  } catch {
    return "right";
  }
}

export function savePlacement(
  placement: InspectorPlacement,
  storage: Pick<Storage, "setItem"> = localStorage,
): void {
  try {
    storage.setItem(PLACEMENT_KEY, placement);
  } catch {
    // Tercih kalıcılaştırılamasa da bu pencerede uygulanır.
  }
}

/** Paylaşılan depo: Ayarlar'daki seçim açık pencereye ANINDA yansımalı. */
const aboneler = new Set<() => void>();
let yer: InspectorPlacement | null = null;

export function subscribePlacement(listener: () => void): () => void {
  aboneler.add(listener);
  return () => {
    aboneler.delete(listener);
  };
}

export function getPlacement(): InspectorPlacement {
  if (yer === null) yer = readPlacement();
  return yer;
}

export function setPlacement(placement: InspectorPlacement): void {
  yer = placement;
  savePlacement(placement);
  for (const listener of aboneler) listener();
}

/** Testlerin depoyu sıfırlaması için; üretimde çağrılmaz. */
export function resetPlacementCache(): void {
  yer = null;
}
