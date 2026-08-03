import React from "react";
import { Composition } from "remotion";
import { FusionTutorial, TOTAL_DURATION } from "./Video";
import { VIDEO } from "./theme";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="FusionTutorial"
    component={FusionTutorial}
    durationInFrames={TOTAL_DURATION}
    fps={VIDEO.fps}
    width={VIDEO.width}
    height={VIDEO.height}
  />
);
