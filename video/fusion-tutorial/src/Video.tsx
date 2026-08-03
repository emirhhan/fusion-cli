import React from "react";
import {
  AbsoluteFill,
  Series,
  useCurrentFrame,
  interpolate,
  useVideoConfig,
} from "remotion";
import { loadFont as loadSans } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

import { S01_Intro } from "./scenes/S01_Intro";
import { S02_WhatIs } from "./scenes/S02_WhatIs";
import { S03_Install } from "./scenes/S03_Install";
import { S04_Engines } from "./scenes/S04_Engines";
import { S05_Mode } from "./scenes/S05_Mode";
import { S06_Effort } from "./scenes/S06_Effort";
import { S07_Models } from "./scenes/S07_Models";
import { S08_Providers } from "./scenes/S08_Providers";
import { S09_Health } from "./scenes/S09_Health";
import { S10_Safety } from "./scenes/S10_Safety";
import { S11_BestPractices } from "./scenes/S11_BestPractices";
import { S12_Outro } from "./scenes/S12_Outro";

// Türkçe için latin-ext şart (ç, ş, ğ, ı, ö, ü); yalnız gereken ağırlıklar yüklenir.
loadSans("normal", {
  weights: ["400", "700", "800"],
  subsets: ["latin", "latin-ext"],
  ignoreTooManyRequestsWarning: true,
});
loadMono("normal", {
  weights: ["400", "700", "800"],
  subsets: ["latin", "latin-ext"],
  ignoreTooManyRequestsWarning: true,
});

// Kenarlarda yumuşak fade — sahneler arası sert kesme olmaz.
const Fade: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = interpolate(
    frame,
    [0, 10, durationInFrames - 12, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

const N = 11; // numaralandırılan öğretim sahnesi sayısı (intro/outro hariç)

const scenes: { d: number; el: React.ReactNode }[] = [
  { d: 130, el: <S01_Intro /> },
  { d: 190, el: <S02_WhatIs i={1} n={N} /> },
  { d: 220, el: <S03_Install i={2} n={N} /> },
  { d: 230, el: <S04_Engines i={3} n={N} /> },
  { d: 235, el: <S05_Mode i={4} n={N} /> },
  { d: 195, el: <S06_Effort i={5} n={N} /> },
  { d: 215, el: <S07_Models i={6} n={N} /> },
  { d: 245, el: <S08_Providers i={7} n={N} /> },
  { d: 175, el: <S09_Health i={8} n={N} /> },
  { d: 180, el: <S10_Safety i={9} n={N} /> },
  { d: 205, el: <S11_BestPractices i={10} n={N} /> },
  { d: 185, el: <S12_Outro /> },
];

export const TOTAL_DURATION = scenes.reduce((a, s) => a + s.d, 0);

export const FusionTutorial: React.FC = () => (
  <Series>
    {scenes.map((s, idx) => (
      <Series.Sequence key={idx} durationInFrames={s.d}>
        <Fade>{s.el}</Fade>
      </Series.Sequence>
    ))}
  </Series>
);
