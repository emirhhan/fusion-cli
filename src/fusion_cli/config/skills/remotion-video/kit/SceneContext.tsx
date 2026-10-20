import {createContext, useContext} from "react";

// Timeline kesmeyi yönetir; bağımsız sahne eski fade davranışını korur.
const SceneContext = createContext(false);
export const TimelineSceneProvider = SceneContext.Provider;
export const useTimelineScene = (): boolean => useContext(SceneContext);
