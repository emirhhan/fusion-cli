import { useSyncExternalStore } from "react";
import { getPlacement, subscribePlacement, type InspectorPlacement } from "./placement";

/** Çalışma panelinin yerini canlı okuyan kanca. */
export function useInspectorPlacement(): InspectorPlacement {
  return useSyncExternalStore(subscribePlacement, getPlacement, getPlacement);
}
