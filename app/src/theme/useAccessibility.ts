import { useSyncExternalStore } from "react";
import { getAccessibilityPreferences, subscribeAccessibility, type ErisilebilirlikTercihleri } from "./accessibility";

/** Erişilebilirlik tercihlerini canlı okuyan kanca. */
export function useAccessibility(): ErisilebilirlikTercihleri {
  return useSyncExternalStore(subscribeAccessibility, getAccessibilityPreferences, getAccessibilityPreferences);
}
