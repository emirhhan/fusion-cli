import { useSyncExternalStore } from "react";
import { getShowSteps, subscribeShowSteps } from "./preferences";

/** Ayarlardaki "adımları göster" tercihini canlı okuyan kanca. */
export function useShowSteps(): boolean {
  return useSyncExternalStore(subscribeShowSteps, getShowSteps, getShowSteps);
}
