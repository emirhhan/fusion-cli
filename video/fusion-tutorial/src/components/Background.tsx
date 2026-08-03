import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { theme } from "../theme";

// Atmosfer: koyu radyal zemin + yavaşça dönen iki gradyan halesi + ince ızgara.
// Compositor dostu: yalnızca transform/opacity animasyonu.
export const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame % 600, [0, 600], [0, 360]);

  return (
    <AbsoluteFill style={{ background: theme.bgGradient }}>
      <AbsoluteFill
        style={{
          opacity: 0.28,
          transform: `rotate(${drift}deg)`,
          background:
            "radial-gradient(40% 40% at 25% 30%, rgba(255,138,61,0.35), transparent 70%)",
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.22,
          transform: `rotate(${-drift}deg)`,
          background:
            "radial-gradient(38% 38% at 78% 72%, rgba(255,77,141,0.35), transparent 70%)",
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.06,
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage:
            "radial-gradient(80% 80% at 50% 40%, black, transparent 85%)",
        }}
      />
    </AbsoluteFill>
  );
};
