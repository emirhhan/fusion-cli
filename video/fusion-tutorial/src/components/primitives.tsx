import React from "react";
import {
  useCurrentFrame,
  interpolate,
  spring,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";

// Gradyan başlık — Fusion kimliğinin turuncu→pembe geçişi.
export const GradientText: React.FC<{
  children: React.ReactNode;
  size?: number;
  weight?: number;
}> = ({ children, size = 96, weight = 800 }) => (
  <span
    style={{
      fontFamily: theme.fontSans,
      fontSize: size,
      fontWeight: weight,
      letterSpacing: -1,
      backgroundImage: theme.gradient,
      WebkitBackgroundClip: "text",
      backgroundClip: "text",
      color: "transparent",
      lineHeight: 1.05,
    }}
  >
    {children}
  </span>
);

// Yay ile aşağıdan yükselerek beliren sarmalayıcı.
export const RiseIn: React.FC<{
  delay?: number;
  children: React.ReactNode;
  y?: number;
}> = ({ delay = 0, children, y = 28 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div
      style={{
        opacity: s,
        transform: `translateY(${interpolate(s, [0, 1], [y, 0])}px)`,
      }}
    >
      {children}
    </div>
  );
};

// Pill rozet — profil/etiket göstergeleri için.
export const Badge: React.FC<{
  children: React.ReactNode;
  color?: string;
  filled?: boolean;
}> = ({ children, color = theme.accent, filled = false }) => (
  <span
    style={{
      fontFamily: theme.fontMono,
      fontSize: 26,
      padding: "6px 16px",
      borderRadius: 999,
      border: `1.5px solid ${color}`,
      color: filled ? theme.bg : color,
      background: filled ? color : "transparent",
      fontWeight: 600,
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </span>
);

// Sahne numarası + başlık (üst şerit).
export const SceneHeader: React.FC<{ index: number; total: number; title: string }> = ({
  index,
  total,
  title,
}) => (
  <RiseIn>
    <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
      <span
        style={{
          fontFamily: theme.fontMono,
          fontSize: 28,
          color: theme.bg,
          background: theme.gradient,
          padding: "4px 14px",
          borderRadius: 10,
          fontWeight: 800,
        }}
      >
        {String(index).padStart(2, "0")}/{String(total).padStart(2, "0")}
      </span>
      <span
        style={{
          fontFamily: theme.fontSans,
          fontSize: 44,
          fontWeight: 700,
          color: theme.text,
          letterSpacing: -0.5,
        }}
      >
        {title}
      </span>
    </div>
  </RiseIn>
);

// Sırayla beliren madde satırı.
export const Bullet: React.FC<{
  delay: number;
  children: React.ReactNode;
  icon?: string;
  color?: string;
}> = ({ delay, children, icon = "▹", color = theme.accent }) => (
  <RiseIn delay={delay} y={18}>
    <div
      style={{
        display: "flex",
        gap: 18,
        alignItems: "baseline",
        fontFamily: theme.fontSans,
        fontSize: 38,
        color: theme.text,
        lineHeight: 1.4,
      }}
    >
      <span style={{ color, fontFamily: theme.fontMono, fontSize: 34 }}>{icon}</span>
      <span>{children}</span>
    </div>
  </RiseIn>
);

// Vurgulu satır içi kod/komut.
export const Code: React.FC<{ children: React.ReactNode; color?: string }> = ({
  children,
  color = theme.accent2,
}) => (
  <span
    style={{
      fontFamily: theme.fontMono,
      fontSize: "0.9em",
      color,
      background: "rgba(255,255,255,0.06)",
      padding: "2px 10px",
      borderRadius: 8,
    }}
  >
    {children}
  </span>
);
