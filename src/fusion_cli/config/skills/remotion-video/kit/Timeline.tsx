import React from "react";
import {AbsoluteFill, Sequence, useVideoConfig} from "remotion";
import {Aurora} from "./Aurora";
import {Particles} from "./Particles";
import {FeatureScene, FeatureSceneProps} from "./FeatureScene";
import {LayoutAudit} from "./LayoutAudit";
import {RuntimeEvidence} from "./RuntimeEvidence";
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
  // Zemin bütün sahnelerin arkasında KESİNTİSİZ akar (sahne kesmesinde atlamaz). Işık
  // lekeleri bilerek kadraj dışına taşar; bu yüzden yerleşim denetiminin dışındadır.
  // Ölçüldü (8 Ekim 2026): FeatureScene sahneleri düz siyahtı, video sadeleşiyordu.
  return <><AbsoluteFill><Aurora intensity={0.4}/><Particles count={45}/></AbsoluteFill>
  <LayoutAudit scope="composition"><RuntimeEvidence>
    {planned.map(({from, scene}) => <Sequence key={scene.id} from={from} durationInFrames={scene.duration}>
      <TimelineSceneProvider value={true}><div data-fusion-scene={scene.id} data-fusion-scene-kind={scene.kind} style={{position: "absolute", inset: 0}}>
        {scene.kind === "feature" ? <FeatureScene {...scene.props}/> : <LayoutAudit><scene.component/></LayoutAudit>}
      </div></TimelineSceneProvider>
    </Sequence>)}
  </RuntimeEvidence></LayoutAudit></>;
};
