import { useSyncExternalStore } from "react";
import { getLanguage, subscribeLanguage, t, type Language, type MetinAnahtari } from "./language";

/** Seçili dili canlı okur ve o dilde çeviren `t`'yi verir. */
export function useLanguage(): { language: Language; t: (key: MetinAnahtari) => string } {
  const language = useSyncExternalStore(subscribeLanguage, getLanguage, getLanguage);
  return { language, t: (key) => t(key, language) };
}
