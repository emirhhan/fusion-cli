import React from "react";
import {Sequence, useVideoConfig} from "remotion";
import {FeatureScene, FeatureSceneProps} from "./FeatureScene";
import {LayoutAudit} from "./LayoutAudit";
import {TimelineSceneProvider} from "./SceneContext";

export type SceneSpec = {id: string; duration: number} & (
  | {kind: "feature"; props: FeatureSceneProps}
  | {kind: "custom"; component: React.ComponentType}
);
export type PlannedScene = {from: number; scene: SceneSpec};

export const planTimeline = (scenes: readonly SceneSpec[], duration: number): PlannedScene[] => {
  const ids = new Set<string>();
  let from = 0;
  const planned = scenes.map(scene => {
    if (!scene.id.trim() || ids.has(scene.id)) throw new Error("Timeline sahne kimlikleri boş olamaz ve benzersiz olmalı.");
    if (!Number.isSafeInteger(scene.duration) || scene.duration <= 0) throw new Error("Timeline sahne süresi pozitif tam kare olmalı.");
    ids.add(scene.id);
    const entry = {from, scene};
    from += scene.duration;
    return entry;
  });
  if (!planned.length || from !== duration) throw new Error("Timeline toplam süresi composition süresiyle aynı olmalı.");
  return planned;
};

// Tek süre sahibi: ardışık kesmeler; opacity boşluğu veya okunabilir sahne örtüşmesi yok.
export const FusionTimeline: React.FC<{scenes: readonly SceneSpec[]}> = ({scenes}) => {
  const {durationInFrames} = useVideoConfig();
  const planned = planTimeline(scenes, durationInFrames);
  return <LayoutAudit scope="composition"><div data-fusion-timeline style={{position: "absolute", inset: 0}}>
    {planned.map(({from, scene}) => <Sequence key={scene.id} from={from} durationInFrames={scene.duration}>
      <TimelineSceneProvider value={true}><div data-fusion-scene={scene.id} style={{position: "absolute", inset: 0}}>
        {scene.kind === "feature" ? <FeatureScene {...scene.props}/> : <LayoutAudit><scene.component/></LayoutAudit>}
      </div></TimelineSceneProvider>
    </Sequence>)}
  </div></LayoutAudit>;
};
